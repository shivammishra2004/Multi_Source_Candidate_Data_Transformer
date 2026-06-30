import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def fixtures_dir(tmp_path):
    """Copy fixtures into a tmp_path so tests never mutate the checked-in originals."""
    dest = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, dest)
    return dest


@pytest.fixture
def recruiter_csv(fixtures_dir):
    return fixtures_dir / "recruiter_export.csv"


@pytest.fixture
def github_urls_file(fixtures_dir):
    return fixtures_dir / "github_urls.txt"


@pytest.fixture
def github_mock_data():
    with open(FIXTURES / "github_api_mocks.json") as f:
        return json.load(f)


@pytest.fixture
def expected_default_output():
    with open(FIXTURES / "expected_default_output.json") as f:
        return json.load(f)


@pytest.fixture
def expected_custom_output():
    with open(FIXTURES / "expected_custom_output.json") as f:
        return json.load(f)


@pytest.fixture
def custom_config():
    with open(FIXTURES / "runtime_config_custom.json") as f:
        return json.load(f)


@pytest.fixture
def mock_github_api(monkeypatch, github_mock_data):
    """
    Monkeypatches requests.get so the GitHub extractor never touches the
    network. Routes /users/{login} and /users/{login}/repos to the fixture
    data, including simulated 404 / 403 responses.
    """
    import requests

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

            # Add headers support for RateLimit checks
            self.headers = {}
            if status_code == 403:
                # Add X-RateLimit-Remaining: 0 to simulate real github behavior
                self.headers["X-RateLimit-Remaining"] = "0"

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} error", response=self)

    def fake_get(url, *args, **kwargs):
        # url looks like https://api.github.com/users/<login> or .../repos
        parts = url.rstrip("/").split("/")
        login = parts[-2] if parts[-1] == "repos" else parts[-1]
        entry = github_mock_data.get(login)

        if entry is None:
            return FakeResponse(404, {"message": "Not Found"})

        if "status_code" in entry:
            return FakeResponse(entry["status_code"], {"message": entry.get("error", "error")})

        if parts[-1] == "repos":
            return FakeResponse(200, entry["repos"])
        return FakeResponse(200, entry["profile"])

    monkeypatch.setattr(requests, "get", fake_get)
    return fake_get
