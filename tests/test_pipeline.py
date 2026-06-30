# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import patch
from src.extractors.csv_extractor import CSVExtractor
from src.extractors.github_extractor import GitHubExtractor
from src.merge_engine import MergeEngine

def test_pipeline_integration(tmp_path):
    csv_path = "tests/mock_data.csv"
    
    urls_path = tmp_path / "urls.txt"
    urls_path.write_text("https://github.com/schen\nhttps://github.com/mike\nhttps://github.com/elena\n")
    
    csv_extractor = CSVExtractor(csv_path, trust_weight=0.5)
    csv_profiles = csv_extractor.extract()
    
    github_extractor = GitHubExtractor(str(urls_path), trust_weight=0.9)
    
    with patch("src.extractors.github_extractor.requests.get") as mock_get:
        def side_effect(url, *args, **kwargs):
            class MockResponse:
                def __init__(self, json_data, status_code=200):
                    self._json_data = json_data
                    self.status_code = status_code
                    self.headers = {}
                def json(self):
                    return self._json_data
            
            if "schen" in url:
                if "repos" in url:
                    return MockResponse([{"language": "Go"}])
                return MockResponse({
                    "name": "Sarah Chen",
                    "email": "s.chen@fictional.io",
                    "company": "TechCorp Global Inc.", 
                    "bio": "Building scalable systems.",
                    "repos_url": "https://api.github.com/users/schen/repos"
                })
            elif "mike" in url:
                if "repos" in url:
                    return MockResponse([{"language": "JavaScript"}])
                return MockResponse({
                    "name": "Michael Lee",
                    "email": None, 
                    "company": "Startup Inc",
                    "repos_url": "https://api.github.com/users/mike/repos"
                })
            elif "elena" in url:
                if "repos" in url:
                    return MockResponse([{"language": "HTML"}])
                return MockResponse({
                    "name": "Elena T.",
                    "email": "elena.t@fictional.io", 
                    "company": "DesignCo",
                    "repos_url": "https://api.github.com/users/elena/repos"
                })
            return MockResponse({}, 404)
            
        mock_get.side_effect = side_effect
        github_profiles = github_extractor.extract()
        
    merger = MergeEngine(variance_penalty=0.05)
    final_profiles = merger.merge_batch([
        ("GitHub", 0.9, github_profiles),
        ("CSV", 0.5, csv_profiles)
    ])
    
    assert len(final_profiles) == 5
    
    sarah = next(p for p in final_profiles if p.full_name == "Sarah Chen")
    mike_csv = next(p for p in final_profiles if p.full_name == "Mike Lee")
    mike_git = next(p for p in final_profiles if p.full_name == "Michael Lee")
    elena_csv = next(p for p in final_profiles if p.full_name == "Elena Typo")
    elena_git = next(p for p in final_profiles if p.full_name == "Elena T.")
    
    # Test A: Sarah
    assert sarah.phones[0] == "+447911123456"
    assert sarah.company == "TechCorp Global Inc."
    skills = {s.name.lower() for s in sarah.skills}
    assert skills == {"python", "aws", "postgres", "go"}
    
    # Test B: Mike
    assert mike_csv.emails[0] == "mike.lee@fictional.io"
    assert len(mike_git.emails) == 0
    
    # Test C: Elena
    assert elena_csv.emails[0] == "elna.t@fictional.io"
    assert elena_git.emails[0] == "elena.t@fictional.io"
