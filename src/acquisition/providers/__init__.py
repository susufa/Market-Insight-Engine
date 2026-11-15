"""
src/acquisition/providers/__init__.py
"""

from src.acquisition.providers.akshare_provider import AKShareProvider
from src.acquisition.providers.mock_provider import MockProvider

__all__ = ["AKShareProvider", "MockProvider"]
