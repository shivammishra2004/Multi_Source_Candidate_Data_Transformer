import logging
from typing import Dict, Type
from .base import BaseExtractor
from .csv_extractor import CSVExtractor
from .github_extractor import GitHubExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_REGISTRY: Dict[str, Type[BaseExtractor]] = {
    'csv': CSVExtractor,
    'github': GitHubExtractor
}

def get_extractor(name: str, file_path: str, trust_weight: float) -> BaseExtractor:
    """
    Dynamically loads and instantiates an extractor based on its registered name.
    """
    cls = EXTRACTOR_REGISTRY.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown extractor source: '{name}'. Available sources: {list(EXTRACTOR_REGISTRY.keys())}")
    
    return cls(file_path=file_path, trust_weight=trust_weight)
