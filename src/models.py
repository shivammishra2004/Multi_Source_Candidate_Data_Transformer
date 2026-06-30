from dataclasses import dataclass, field
from typing import List, Optional, Dict

@dataclass
class Location:
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None

@dataclass
class Links:
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = field(default_factory=list)

@dataclass
class Skill:
    name: str
    confidence: float
    sources: List[str] = field(default_factory=list)

@dataclass
class Experience:
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None    # YYYY-MM
    summary: Optional[str] = None

@dataclass
class Education:
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[str] = None

@dataclass
class Provenance:
    field: str
    source: str
    method: str
    confidence: float

@dataclass
class CanonicalProfile:
    candidate_id: str = ""
    full_name: str = ""
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location: Location = field(default_factory=Location)
    links: Links = field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = field(default_factory=list)
    experience: List[Experience] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    provenance: List[Provenance] = field(default_factory=list)
    overall_confidence: float = 0.0

    def to_dict(self) -> dict:
        """
        Helper to cleanly convert this dataclass to a dictionary
        while handling nested dataclasses correctly.
        """
        from dataclasses import asdict
        return asdict(self)
