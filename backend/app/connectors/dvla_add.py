"""DVLA Access to Driver Data (ADD) connector — driving licence verification.

Implements the DVLA secure API pattern (developer-portal.driver-vehicle-
licensing.api.gov.uk):

1. POST /thirdparty-access/v1/authenticate with userName/password
   -> JWT (`id-token`), valid for 1 hour. Cached and reused; refreshed
   automatically shortly before expiry or after a 401.
2. POST /full-driver-enquiry/v1/driving-licences/retrieve with
   {"drivingLicenceNumber": ...} and headers `x-api-key` + `Authorization`.

Access requires a commercial agreement with DVLA — credentials are issued per
consumer and processing is based on the driver's consent (recorded in the
audit log at submission). The base URL defaults to DVLA's UAT environment;
set DVLA_API_BASE_URL for production.

Data minimisation: only licence status, entitlement categories, endorsements
and disqualifications are surfaced. The driver's address and gender returned
by the API are deliberately not stored, and the licence number itself never
appears in logs, findings, or error messages.
"""

import logging
import time
from typing import Any

import httpx

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

logger = logging.getLogger(__name__)

_AUTH_PATH = "/thirdparty-access/v1/authenticate"
_RETRIEVE_PATH = "/full-driver-enquiry/v1/driving-licences/retrieve"

# JWTs last 1 hour; refresh with a safety margin.
_TOKEN_TTL_SECONDS = 55 * 60

_SOURCE_URL = (
    "https://developer-portal.driver-vehicle-licensing.api.gov.uk/apis/driver-view/"
    "driver-view-description.html"
)

# Licence statuses that constitute an adverse verification result.
_ADVERSE_STATUSES = {"revoked", "expired", "surrendered", "disqualified", "refused"}


class DvlaAddConnector(BaseConnector):
    name = "dvla_add"
    display_name = "DVLA Driving Licence (ADD)"
    description = (
        "Driving licence verification via the DVLA Access to Driver Data API: "
        "validity, entitlements, endorsements, and disqualifications. Runs only "
        "when a licence number is supplied with driver consent."
    )

    _token: str | None = None
    _token_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(
            self.settings.dvla_username
            and self.settings.dvla_password
            and self.settings.dvla_api_key
        )

    def applies_to(self, subject: SearchSubject) -> bool:
        return bool(subject.driving_licence_number)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.dvla_mock(subject)

    # -- auth --------------------------------------------------------------------

    async def _get_token(self, client: httpx.AsyncClient, force: bool = False) -> str:
        cls = type(self)
        if (
            not force
            and cls._token
            and time.monotonic() - cls._token_at < _TOKEN_TTL_SECONDS
        ):
            return cls._token
        resp = await client.post(
            f"{self.settings.dvla_api_base_url}{_AUTH_PATH}",
            json={
                "userName": self.settings.dvla_username,
                "password": self.settings.dvla_password,
            },
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        cls._token = resp.json()["id-token"]
        cls._token_at = time.monotonic()
        return cls._token

    async def _retrieve(
        self, client: httpx.AsyncClient, licence_number: str
    ) -> httpx.Response:
        token = await self._get_token(client)
        headers = {
            "x-api-key": self.settings.dvla_api_key,
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = await client.post(
            f"{self.settings.dvla_api_base_url}{_RETRIEVE_PATH}",
            json={"drivingLicenceNumber": licence_number},
            headers=headers,
        )
        if resp.status_code == 401:
            # Token likely expired mid-window — refresh once and retry.
            headers["Authorization"] = await self._get_token(client, force=True)
            resp = await client.post(
                f"{self.settings.dvla_api_base_url}{_RETRIEVE_PATH}",
                json={"drivingLicenceNumber": licence_number},
                headers=headers,
            )
        return resp

    # -- findings ----------------------------------------------------------------

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        resp = await self._retrieve(client, subject.driving_licence_number)

        if resp.status_code == 404:
            # A definitive "no such licence" is itself a verification result,
            # not a connector failure.
            return [
                Finding(
                    source=self.name,
                    category=Category.DRIVING_LICENCE_ISSUE,
                    title="Driving licence not found",
                    description=(
                        "DVLA holds no record for the supplied driving licence "
                        "number. The number may be mistyped, invalid, or not a "
                        "GB licence."
                    ),
                    url=_SOURCE_URL,
                    raw={"dvla_status": "not_found"},
                )
            ]
        resp.raise_for_status()
        return self._parse(resp.json())

    def _parse(self, data: dict[str, Any]) -> list[Finding]:
        driver = data.get("driver") or {}
        licence = data.get("licence") or {}
        # Name/DOB from the record corroborate identity via the matching
        # engine; the returned address and gender are deliberately unused.
        record_name = " ".join(
            p for p in [driver.get("firstNames"), driver.get("lastName")] if p
        ) or None
        record_dob = driver.get("dateOfBirth")

        findings: list[Finding] = []
        status = (licence.get("status") or "unknown").strip()
        licence_type = (licence.get("type") or "").strip()
        adverse_status = status.lower() in _ADVERSE_STATUSES
        findings.append(
            Finding(
                source=self.name,
                category=(
                    Category.DRIVING_LICENCE_ISSUE
                    if adverse_status
                    else Category.DRIVING_LICENCE
                ),
                title=f"Driving licence verified — status: {status}",
                description=(
                    f"{licence_type or 'Licence'} licence, status {status}. "
                    f"Entitlement categories: "
                    f"{', '.join(self._category_codes(data)) or 'none returned'}."
                ),
                url=_SOURCE_URL,
                subject_name=record_name,
                date_of_birth=record_dob,
                raw={"licence_status": status, "licence_type": licence_type},
            )
        )

        for endorsement in data.get("endorsements") or []:
            offence_code = endorsement.get("offenceCode") or "endorsement"
            points = endorsement.get("penaltyPoints")
            disqualification = endorsement.get("disqualification") or {}
            is_disqualification = bool(disqualification) or "disqual" in str(
                endorsement.get("offenceLegalLiteral") or ""
            ).lower()
            title = f"Driving endorsement {offence_code}"
            if points:
                title += f" — {points} penalty points"
            if is_disqualification:
                title = f"Driving disqualification — {offence_code}"
            findings.append(
                Finding(
                    source=self.name,
                    category=(
                        Category.DRIVING_DISQUALIFICATION
                        if is_disqualification
                        else Category.DRIVING_ENDORSEMENT
                    ),
                    title=title,
                    description=endorsement.get("offenceLegalLiteral"),
                    url=_SOURCE_URL,
                    date=endorsement.get("offenceDate"),
                    subject_name=record_name,
                    date_of_birth=record_dob,
                    raw={
                        "offence_code": offence_code,
                        "penalty_points": points,
                        "disqualification": disqualification or None,
                    },
                )
            )
        return findings

    @staticmethod
    def _category_codes(data: dict[str, Any]) -> list[str]:
        return [
            e.get("categoryCode")
            for e in (data.get("entitlements") or [])
            if e.get("categoryCode")
        ]
