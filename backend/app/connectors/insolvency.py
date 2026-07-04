"""UK Individual Insolvency Register connector.

There is no stable free public API for the Individual Insolvency Register, so
this connector targets a configurable licensed-provider endpoint
(`INSOLVENCY_API_URL` / `INSOLVENCY_API_KEY`). The expected response shape is a
JSON body with a `records` array; adjust `_parse` for your provider. In mock
mode realistic fixtures are returned instead.
"""

import httpx

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject


class InsolvencyConnector(BaseConnector):
    name = "insolvency_register"
    display_name = "UK Insolvency Register"
    description = "Bankruptcies and insolvency records (licensed provider endpoint)."

    def is_configured(self) -> bool:
        return bool(self.settings.insolvency_api_url)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.insolvency_mock(subject)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        headers = {}
        if self.settings.insolvency_api_key:
            headers["Authorization"] = f"Bearer {self.settings.insolvency_api_key}"
        resp = await client.get(
            self.settings.insolvency_api_url,
            params={"name": subject.full_name},
            headers=headers,
        )
        resp.raise_for_status()
        return self._parse(resp.json(), subject)

    def _parse(self, data: dict, subject: SearchSubject) -> list[Finding]:
        findings = []
        for record in data.get("records", []):
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.INSOLVENCY,
                    title=record.get("title")
                    or f"Insolvency record — {record.get('name', subject.full_name)}",
                    description=record.get("description") or record.get("order_type"),
                    url=record.get("url"),
                    date=record.get("date"),
                    subject_name=record.get("name"),
                    location=record.get("address"),
                    date_of_birth=record.get("date_of_birth"),
                    raw=record,
                )
            )
        return findings
