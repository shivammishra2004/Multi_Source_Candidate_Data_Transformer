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
        Step 1: Sanitize. Strip out all spaces, dashes, parentheses, and letters.
        Step 2: Check for the '+'. If it was at the beginning, keep it.
        Step 3: If no '+' and exactly 10 digits, assume standard US/IN (+1/+91).
                We will default to US (+1) as requested.
        """
        if not phone:
            return None
        
        has_plus = phone.strip().startswith('+')
        # Strip everything that is not a digit
        digits = re.sub(r'\D', '', phone)
        
        if not digits:
            return None
            
        if has_plus:
            return f"+{digits}"
        
        if len(digits) == 10:
            # Assumption: 10 digit numbers without a country code are US numbers (+1)
            logger.debug(f"Normalizer: Assuming +1 for 10-digit number {phone}")
            return f"+1{digits}"
            
        return digits

    @staticmethod
    def normalize_email(email: str) -> Optional[str]:
        if not email:
            return None
        return email.strip().lower()

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
                return dt.strftime("%Y-%m")
            except ValueError:
                continue
                
        logger.debug(f"Normalizer: Could not parse date format for '{date_str}'")
        return date_str
