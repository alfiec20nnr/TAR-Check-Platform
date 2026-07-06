"""Connector registry.

Discovers and runs connectors. Adding a new data source means writing a
BaseConnector subclass and appending it to CONNECTOR_CLASSES — nothing in the
core pipeline changes.
"""

import asyncio

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

CONNECTOR_CLASSES: list[type[BaseConnector]] = [
    BraveSearchConnector,
    GoogleSearchConnector,
    NewsApiConnector,
    CompaniesHouseConnector,
    InsolvencyConnector,
    UkSanctionsConnector,
    FcaWarningConnector,
    DvlaAddConnector,
]


class ConnectorRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.connectors: list[BaseConnector] = [cls(settings) for cls in CONNECTOR_CLASSES]

    def list_metadata(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "display_name": c.display_name,
                "description": c.description,
                "enabled": True,
            }
            for c in self.connectors
        ]

    async def run_all(
        self, subject: SearchSubject, enabled_names: set[str] | None = None
    ) -> list[ConnectorResult]:
        """Run enabled connectors concurrently; one slow/failing source never
        blocks the others."""
        selected = [
            c
            for c in self.connectors
            if enabled_names is None or c.name in enabled_names
        ]
        return list(await asyncio.gather(*(c.run(subject) for c in selected)))


def get_registry(settings: Settings | None = None) -> ConnectorRegistry:
    return ConnectorRegistry(settings or get_settings())
