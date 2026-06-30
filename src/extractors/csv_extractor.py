import csv
import logging
from typing import List
from .base import BaseExtractor
from ..models import CanonicalProfile, Experience
from ..normalizer import Normalizer

logger = logging.getLogger(__name__)

class CSVExtractor(BaseExtractor):
    def __init__(self, file_path: str, trust_weight: float = 0.5):
        super().__init__(trust_weight)
        self.file_path = file_path

    @property
    def source_name(self) -> str:
        return "CSV"

    def extract(self) -> List[CanonicalProfile]:
        profiles = []
        try:
            with open(self.file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Clean keys (lowercase, strip)
                    cleaned_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v.strip()}
                    if not cleaned_row:
                        continue
                    
                    profile = CanonicalProfile()
                    # We will do greedy extraction: if something is missing, just don't set it (leave as default)
                    
                    if 'name' in cleaned_row:
                        profile.full_name = cleaned_row['name']
                    
                    if 'email' in cleaned_row:
                        norm_email = Normalizer.normalize_email(cleaned_row['email'])
                        if norm_email: profile.emails.append(norm_email)
                    
                    if 'phone' in cleaned_row:
                        norm_phone = Normalizer.format_phone(cleaned_row['phone'])
                        if norm_phone: profile.phones.append(norm_phone)
                        
                    if 'github' in cleaned_row:
                        norm_github = Normalizer.normalize_url(cleaned_row['github'])
                        if norm_github: profile.links.github = norm_github
                        
                    company = cleaned_row.get('current_company')
                    title = cleaned_row.get('title')
                    start = cleaned_row.get('start_date')
                    end = cleaned_row.get('end_date')
                    
                    if company:
                        profile.company = company
                        
                    if company or title:
                        start_norm = Normalizer.normalize_date(start) if start else None
                        end_norm = Normalizer.normalize_date(end) if end else None
                        exp = Experience(company=company, title=title, start=start_norm, end=end_norm)
                        profile.experience.append(exp)
                        
                    # Also extract skills if present in CSV, as comma separated
                    if 'skills' in cleaned_row:
                        from ..models import Skill
                        skills_list = [s.strip() for s in cleaned_row['skills'].split(',')]
                        for s in Normalizer.normalize_skills(skills_list):
                            profile.skills.append(Skill(name=s, confidence=self.trust_weight))

                    profiles.append(profile)
                    
        except Exception as e:
            logger.warning(f"Failed to read or parse CSV {self.file_path}: {e}")
            
        return profiles
