"""core/interfaces package – re-export all abstract contracts."""

from core.interfaces.data_source import BaseDataSourceAdapter
from core.interfaces.predictor import BasePredictor, PredictionResult
from core.interfaces.quality import BaseQualityValidator
from core.interfaces.storage import BaseStorageEngine

__all__ = [
    "BaseDataSourceAdapter",
    "BaseStorageEngine",
    "BaseQualityValidator",
    "BasePredictor",
    "PredictionResult",
]
