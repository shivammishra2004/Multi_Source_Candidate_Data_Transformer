import re
import logging
from typing import Optional, List, Set
from datetime import datetime
from .models import Skill

logger = logging.getLogger(__name__)

class Normalizer:
    @staticmethod
    def format_phone(phone: str) -> Optional[str]:
        """
        Formats phone numbers into E.164 using the phonenumbers library.
        Defaults to US (+1) for parsing if no country code is specified.
        """
        if not phone:
            return None
            
        try:
            import phonenumbers
            # Parse with US region as default for numbers without a country code
            parsed = phonenumbers.parse(phone, "US")
            
            # For 7 digit numbers, is_possible_number is true but is_valid_number might be false
            # without an area code. For ATS we want valid, callable E.164 numbers.
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            logger.debug(f"Normalizer: Failed to parse phone number '{phone}': {e}")
            
        return None

    @staticmethod
    def normalize_email(email: str) -> Optional[str]:
        if not email:
            return None
        email = email.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            return None
        return email

    @staticmethod
    def normalize_url(url: str) -> Optional[str]:
        if not url:
            return None
        url = url.strip().lower()
        # Remove trailing slash
        if url.endswith('/'):
            url = url[:-1]
        # Remove schema
        if url.startswith('https://'):
            url = url[8:]
        elif url.startswith('http://'):
            url = url[7:]
        # Remove www.
        if url.startswith('www.'):
            url = url[4:]
        return url

    @staticmethod
    def normalize_skills(skills: List[str]) -> Set[str]:
        """
        Takes a list of raw skill strings, lowercases them, 
        strips whitespace, and returns a unique set.
        """
        normalized = set()
        for s in skills:
            if not s:
                continue
            clean = s.strip().lower()
            if clean:
                normalized.add(clean)
        return normalized

    @staticmethod
    def normalize_skill(skill: str) -> Optional[str]:
        res = Normalizer.normalize_skills([skill])
        return list(res)[0] if res else None

    @staticmethod
    def normalize_country(country: str) -> Optional[str]:
        # Stub for future implementation
        return None

    @staticmethod
    def normalize_date_range(date_str: str) -> tuple:
        # Stub for future implementation
        return (None, None)

    @staticmethod
    def normalize_name(name: str) -> Optional[str]:
        if not name:
            return None
        # Replace multiple spaces with a single space
        return re.sub(r'\s+', ' ', name.strip())

    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        """
        Attempts to parse a date string and return it in YYYY-MM format.
        Handles variations like '05/2020', 'May 2020', '2020-05', '2020'.
        """
        if not date_str:
            return None
            
        date_str = date_str.strip()
        
        # Define formats to try (most specific to least specific)
        formats = [
            "%Y-%m-%d",  # 2020-05-15
            "%Y-%m",     # 2020-05
            "%m/%Y",     # 05/2020
            "%m/%d/%Y",  # 05/15/2020
            "%b %Y",     # May 2020
            "%B %Y",     # May 2020 (full name)
            "%Y",        # 2020
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if fmt == "%Y":
                    return None
                return dt.strftime("%Y-%m")
            except ValueError:
                continue
                
        logger.debug(f"Normalizer: Could not parse date format for '{date_str}'")
        return None
