"""
tests/unit/test_mock_provider_isolation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verification of Directive 3: MockProvider Production Environment Isolation.
"""

import pytest

from src.acquisition.providers.akshare_provider import AKShareProvider
from src.acquisition.providers.mock_provider import MockProvider
from src.acquisition.registry import (
    ProviderNotFoundError,
    ProviderRegistrationError,
    ProviderRegistry,
)
from src.core.entities import Market


def test_mock_provider_blocked_in_production():
    """Verify that MockProvider cannot be registered in production environment."""
    registry = ProviderRegistry(environment="production", allow_mock=False)
    mock_p = MockProvider()

    with pytest.raises(ProviderRegistrationError, match="strictly prohibited in 'production'"):
        registry.register(mock_p)


def test_mock_provider_blocked_if_allow_mock_is_false():
    """Verify that MockProvider cannot be registered when allow_mock=False even in dev."""
    registry = ProviderRegistry(environment="development", allow_mock=False)
    mock_p = MockProvider()

    with pytest.raises(ProviderRegistrationError, match="strictly prohibited"):
        registry.register(mock_p)


def test_mock_provider_allowed_in_test_env_when_explicit():
    """Verify that MockProvider can be registered when environment='test' and allow_mock=True."""
    registry = ProviderRegistry(environment="test", allow_mock=True)
    mock_p = MockProvider()

    # Should succeed without raising
    registry.register(mock_p)
    assert "mock" in registry.list_providers()
    retrieved = registry.get_provider("mock")
    assert retrieved.provider_id == "mock"


def test_real_provider_allowed_in_all_environments():
    """Verify that real providers (e.g. AKShareProvider) can register in production."""
    registry = ProviderRegistry(environment="production", allow_mock=False)
    ak_p = AKShareProvider()

    registry.register(ak_p)
    assert "akshare" in registry.list_providers()
    assert registry.get_primary_provider(Market.CN_A) is ak_p


def test_get_provider_not_found():
    """Verify non-existent provider raises ProviderNotFoundError."""
    registry = ProviderRegistry(environment="production", allow_mock=False)
    with pytest.raises(ProviderNotFoundError):
        registry.get_provider("non_existent")
