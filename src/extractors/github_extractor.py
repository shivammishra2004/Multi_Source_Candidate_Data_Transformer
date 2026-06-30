import logging
import requests
import os
import time
from typing import List
import concurrent.futures
from .base import BaseExtractor
from ..models import CanonicalProfile, Skill

logger = logging.getLogger(__name__)

class GitHubExtractor(BaseExtractor):
    def __init__(self, file_path: str, trust_weight: float = 0.9, max_workers: int = 5):
        super().__init__(trust_weight)
        self.file_path = file_path
        self.max_workers = max_workers

    @property
    def source_name(self) -> str:
        return "GitHub"

    def _fetch_profile(self, url: str) -> List[CanonicalProfile]:
        profiles = []
        try:
            url = url.strip()
            if not url:
                return profiles

            # Simulated API call for GitHub User
            # Extract username from url (e.g. https://github.com/torvalds -> torvalds)
            username = url.rstrip('/').split('/')[-1]
            api_url = f"https://api.github.com/users/{username}"
            
            headers = {"Accept": "application/vnd.github.v3+json"}
            token = os.getenv("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
                
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    logger.error(f"GitHub API rate limit exceeded for {url}.")
                    return profiles
                else:
                    logger.warning(f"Secondary rate limit hit for {url}. Backing off.")
                    time.sleep(2)
                    response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                profile = CanonicalProfile()
                
                if data.get('email'):
                    profile.emails.append(data.get('email'))
                    
                if data.get('name'):
                    profile.full_name = data.get('name')
                elif data.get('login'):
                    profile.full_name = data.get('login')
                
                if data.get('location'):
                    profile.location.city = data.get('location')
                
                if data.get('blog'):
                    profile.links.portfolio = data.get('blog')
                
                if data.get('company'):
                    profile.company = data.get('company')
                
                profile.links.github = url
                    
                if data.get('bio'):
                    profile.headline = data.get('bio')
                
                # Fetch repos to extract skills (languages)
                repos_url = data.get('repos_url')
                if repos_url:
                    repos_response = requests.get(repos_url, headers=headers, timeout=10)
                    if repos_response.status_code == 403:
                        if repos_response.headers.get("X-RateLimit-Remaining") != "0":
                            time.sleep(2)
                            repos_response = requests.get(repos_url, headers=headers, timeout=10)
                    if repos_response.status_code == 200:
                        repos_data = repos_response.json()
                        languages = set()
                        for repo in repos_data:
                            lang = repo.get('language')
                            if lang:
                                languages.add(lang)
                        
                        from ..normalizer import Normalizer
                        for lang in Normalizer.normalize_skills(list(languages)):
                            profile.skills.append(Skill(name=lang, confidence=self.trust_weight))

                profiles.append(profile)
            else:
                logger.warning(f"GitHub API returned {response.status_code} for user {username}")
                
        except Exception as e:
            logger.warning(f"Failed to fetch or parse GitHub data for {url}: {e}")

        return profiles

    def extract(self) -> List[CanonicalProfile]:
        all_profiles = []
        try:
            with open(self.file_path, mode='r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Process URLs concurrently
                future_to_url = {executor.submit(self._fetch_profile, url): url for url in urls}
                for future in future_to_url:
                    profiles = future.result()
                    all_profiles.extend(profiles)
                    
        except Exception as e:
            logger.warning(f"Failed to read GitHub urls file {self.file_path}: {e}")
            
        return all_profiles
