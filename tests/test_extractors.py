from unittest.mock import patch
from src.extractors.github_extractor import GitHubExtractor

@patch('src.extractors.github_extractor.requests.get')
def test_github_extractor_handles_missing_email(mock_get):
    # 1. ARRANGE: Set up the fake JSON payload you want the "API" to return
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "name": "Michael Lee",
        "email": None,  # Simulating a private email profile
        "company": "Startup Inc"
    }
    
    # We pass a dummy file path since it's required by the constructor, though we are testing _fetch_profile directly here.
    extractor = GitHubExtractor("dummy_url.txt")
    
    # 2. ACT: When this runs, it hits your fake mock_get, not the real internet
    profiles = extractor._fetch_profile("https://api.github.com/users/mike")
    
    # Since _fetch_profile returns a List[CanonicalProfile], get the first one.
    profile = profiles[0]
    
    # 3. ASSERT
    assert profile.full_name == "Michael Lee"
    assert profile.emails == []  # Ensure it handles the null gracefully
