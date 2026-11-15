"""
src/acquisition/__init__.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Modular Data Acquisition Subsystem.
"""

from src.acquisition.base import (
    BaseProvider,
    RawProviderResponse,
    VolumeNormalizationSpec,
    VolumeUnit,
)
from src.acquisition.normalizer import BarNormalizer
from src.acquisition.registry import (
    ProviderNotFoundError,
    ProviderRegistrationError,
    ProviderRegistry,
)

__all__ = [
    "BaseProvider",
    "RawProviderResponse",
    "VolumeUnit",
    "VolumeNormalizationSpec",
    "BarNormalizer",
    "ProviderRegistry",
    "ProviderRegistrationError",
    "ProviderNotFoundError",
]
