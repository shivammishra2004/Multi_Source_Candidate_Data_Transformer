from abc import ABC, abstractmethod
from typing import List, Any
from ..models import CanonicalProfile

class BaseExtractor(ABC):
    def __init__(self, trust_weight: float):
        self.trust_weight = trust_weight

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the source (e.g., 'GitHub', 'CSV')."""
        pass

    @abstractmethod
    def extract(self) -> List[CanonicalProfile]:
        """
        Extract data from the source and return a list of CanonicalProfiles.
        If extraction fails or data is garbage, it should handle it gracefully,
        yielding what it can or returning an empty list, logging warnings as needed.
        """
        pass
