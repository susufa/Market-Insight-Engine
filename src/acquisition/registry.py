"""
src/acquisition/registry.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Central registry and lifecycle manager for data providers,
enforcing strict production environment isolation against MockProvider.
"""

from __future__ import annotations

import logging

from src.acquisition.base import BaseProvider
from src.core.entities import Market

logger = logging.getLogger("ProviderRegistry")


class ProviderRegistrationError(Exception):
    """Raised when provider registration violates security or policy rules."""

    pass


class ProviderNotFoundError(Exception):
    """Raised when a requested provider is not found or not permitted."""

    pass


class ProviderRegistry:
    """
    Registry for managing available data providers with market routing
    and production security guardrails.
    """

    def __init__(
        self,
        environment: str = "production",
        allow_mock: bool = False,
    ) -> None:
        self._environment = environment.lower().strip()
        self._allow_mock = allow_mock
        self._providers: dict[str, BaseProvider] = {}
        self._market_routing: dict[Market, list[str]] = {
            Market.CN_A: [],
            Market.CN_HK: [],
            Market.INDEX: [],
        }

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def allow_mock(self) -> bool:
        return self._allow_mock

    def register(self, provider: BaseProvider, priority: int = 0) -> None:
        """
        Register a provider instance.
        Enforces Directive 3: MockProvider is strictly prohibited in production.
        """
        pid = provider.provider_id.lower().strip()

        # Directive 3: Strict production isolation for mock
        if pid == "mock" and (self._environment == "production" or not self._allow_mock):
            error_msg = (
                f"Security Error: MockProvider registration rejected. "
                f"Mock providers are strictly prohibited in '{self._environment}' environment "
                f"(allow_mock={self._allow_mock})."
            )
            logger.error(error_msg)
            raise ProviderRegistrationError(error_msg)

        if pid in self._providers:
            logger.info("Overwriting existing provider registration for '%s'", pid)

        self._providers[pid] = provider

        # Update market routing tables
        for market in provider.supported_markets:
            if market not in self._market_routing:
                self._market_routing[market] = []
            if pid not in self._market_routing[market]:
                if priority > 0:
                    self._market_routing[market].insert(0, pid)
                else:
                    self._market_routing[market].append(pid)

        logger.info(
            "Registered provider '%s' (markets: %s, env: %s)",
            pid,
            [m.value for m in provider.supported_markets],
            self._environment,
        )

    def get_provider(self, provider_id: str) -> BaseProvider:
        """Retrieve a registered provider by its identifier."""
        pid = provider_id.lower().strip()
        if pid == "mock" and (self._environment == "production" or not self._allow_mock):
            raise ProviderRegistrationError(
                f"Access Denied: MockProvider forbidden in '{self._environment}' environment."
            )

        if pid not in self._providers:
            raise ProviderNotFoundError(f"Provider '{provider_id}' is not registered.")
        return self._providers[pid]

    def list_providers(self) -> list[str]:
        """Return list of active registered provider IDs."""
        return list(self._providers.keys())

    def get_providers_for_market(self, market: Market) -> list[BaseProvider]:
        """Return ordered list of providers capable of serving the specified market."""
        pids = self._market_routing.get(market, [])
        return [self._providers[pid] for pid in pids if pid in self._providers]

    def get_primary_provider(self, market: Market) -> BaseProvider | None:
        """Return the primary (first priority) provider for the market."""
        providers = self.get_providers_for_market(market)
        return providers[0] if providers else None
