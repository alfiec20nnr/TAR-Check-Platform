"""Connector registry.

Discovers and runs connectors. Adding a new data source means writing a
BaseConnector subclass and appending it to CONNECTOR_CLASSES — nothing in the
core pipeline changes.
"""

import asyncio
from collections.abc import Awaitable, Callable

from app.config import Settings, get_settings
from app.connectors.base import BaseConnector, ConnectorResult, SearchSubject
from app.connectors.brave_search import BraveSearchConnector
from app.connectors.companies_house import CompaniesHouseConnector
from app.connectors.dvla_add import DvlaAddConnector
from app.connectors.fca_warning import FcaWarningConnector
from app.connectors.google_search import GoogleSearchConnector
from app.connectors.insolvency import InsolvencyConnector
from app.connectors.news_api import NewsApiConnector
from app.connectors.sanctions import UkSanctionsConnector
from app.connectors.social_media import SocialMediaConnector
from app.connectors.uk_newspapers import UkNewspapersConnector

# Listed in PRIORITY ORDER (highest first). All connectors still run
# concurrently, but priority decides:
#   - who gets the shared Brave request budget first (1 req/s),
#   - which copy survives when the same result comes from several sources,
#   - the order sources are listed in results and reports.
CONNECTOR_CLASSES: list[type[BaseConnector]] = [
    BraveSearchConnector,  # 1 — general web
    UkNewspapersConnector,  # 2 — UK national/regional press
    NewsApiConnector,  # 3 — news coverage
    DvlaAddConnector,  # 4 — driving licence (only with a licence number)
    UkSanctionsConnector,  # then by severity of what each source can find
    CompaniesHouseConnector,
    InsolvencyConnector,
    FcaWarningConnector,
    SocialMediaConnector,
    GoogleSearchConnector,  # closed to new customers; Brave covers the web
]


class ConnectorRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.connectors: list[BaseConnector] = []
        for priority, cls in enumerate(CONNECTOR_CLASSES, start=1):
            connector = cls(settings)
            connector.priority = priority
            self.connectors.append(connector)

    def list_metadata(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "display_name": c.display_name,
                "description": c.description,
                "enabled": True,
                "priority": c.priority,
            }
            for c in self.connectors
        ]

    async def run_all(
        self,
        subject: SearchSubject,
        enabled_names: set[str] | None = None,
        on_progress: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> list[ConnectorResult]:
        """Run enabled connectors concurrently; one slow/failing source never
        blocks the others.

        ``on_progress(done, total, connector_name)`` is awaited each time a
        connector finishes, so callers can report progress.
        """
        selected = [
            c
            for c in self.connectors
            if enabled_names is None or c.name in enabled_names
        ]
        total = len(selected)
        done = 0

        async def _run(connector: BaseConnector) -> ConnectorResult:
            nonlocal done
            result = await connector.run(subject)
            done += 1
            if on_progress is not None:
                await on_progress(done, total, connector.display_name)
            return result

        return list(await asyncio.gather(*(_run(c) for c in selected)))


def get_registry(settings: Settings | None = None) -> ConnectorRegistry:
    return ConnectorRegistry(settings or get_settings())
