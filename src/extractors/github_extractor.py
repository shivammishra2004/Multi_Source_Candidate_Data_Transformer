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
        self.additional_urls: List[str] = []

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
                
            def _http_get(req_url, **kwargs):
                mock_file = os.getenv("GITHUB_MOCK_FILE")
                if mock_file and os.path.exists(mock_file):
                    import json
                    with open(mock_file, 'r', encoding='utf-8') as f:
                        mock_data = json.load(f)
                    
                    parts = req_url.rstrip("/").split("/")
                    login = parts[-2] if parts[-1] == "repos" else parts[-1]
                    entry = mock_data.get(login)
                    
                    class FakeResponse:
                        def __init__(self, status_code, payload):
                            self.status_code = status_code
                            self._payload = payload
                            self.headers = {"X-RateLimit-Remaining": "0"} if status_code == 403 else {}
                        def json(self):
                            return self._payload

                    if entry is not None:
                        if "status_code" in entry:
                            return FakeResponse(entry["status_code"], {"message": entry.get("error", "error")})
                        if parts[-1] == "repos":
                            return FakeResponse(200, entry.get("repos", []))
                        return FakeResponse(200, entry.get("profile", entry))
                    else:
                        return FakeResponse(404, {"message": "Not Found (Mocked)"})
                        
                return requests.get(req_url, **kwargs)
                
            response = _http_get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    logger.error(f"GitHub API rate limit exceeded for {url}.")
                    return profiles
                else:
                    logger.warning(f"Secondary rate limit hit for {url}. Backing off.")
                    time.sleep(2)
                    response = _http_get(api_url, headers=headers, timeout=10)
            
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
                
                from ..normalizer import Normalizer
                norm_github = Normalizer.normalize_url(url)
                profile.links.github = norm_github if norm_github else url
                    
                if data.get('bio'):
                    profile.headline = data.get('bio')
                
                # Fetch repos to extract skills (languages)
                repos_url = data.get('repos_url', f"https://api.github.com/users/{username}/repos")
                if repos_url:
                    repos_response = _http_get(repos_url, headers=headers, timeout=10)
                    if repos_response.status_code == 403:
                        if repos_response.headers.get("X-RateLimit-Remaining") != "0":
                            time.sleep(2)
                            repos_response = _http_get(repos_url, headers=headers, timeout=10)
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
            urls = []
            if self.file_path and os.path.exists(self.file_path):
                with open(self.file_path, mode='r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip()]
            
            if hasattr(self, 'additional_urls') and self.additional_urls:
                urls.extend(self.additional_urls)
            
            # Deduplicate urls by username
            unique_urls = []
            seen_usernames = set()
            for u in urls:
                if not u.strip(): continue
                username = u.strip().rstrip('/').split('/')[-1]
                if username not in seen_usernames:
                    seen_usernames.add(username)
                    unique_urls.append(u)
            urls = unique_urls
            
            if not urls:
                return all_profiles
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Process URLs concurrently
                future_to_url = {executor.submit(self._fetch_profile, url): url for url in urls}
                for future in future_to_url:
                    profiles = future.result()
                    all_profiles.extend(profiles)
                    
        except Exception as e:
            logger.warning(f"Failed to read GitHub urls file {self.file_path}: {e}")
            
        return all_profiles
