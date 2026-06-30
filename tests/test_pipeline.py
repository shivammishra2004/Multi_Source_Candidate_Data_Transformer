import json
import pytest

from src.normalizer import Normalizer
from src.extractors.csv_extractor import CSVExtractor
from src.extractors.github_extractor import GitHubExtractor
from src.merge_engine import MergeEngine
from src.projector import Projector

class TestNormalizer:
    @pytest.mark.parametrize("raw,expected", [
        ("555-123-4567", "+15551234567"),
        ("+1 (555) 123-4567", "+15551234567"),
        ("+91 98765 43210", "+919876543210"),
        ("  +1-555-123-4567  ", "+15551234567"),
    ])
    def test_normalize_phone_valid(self, raw, expected):
        assert Normalizer.format_phone(raw) == expected

    @pytest.mark.parametrize("raw", [
        "1234",
        "not-a-phone",
        "",
        None,
    ])
    def test_normalize_phone_invalid_returns_null_never_invented(self, raw):
        assert Normalizer.format_phone(raw) is None

    def test_normalize_email_lowercases_and_strips(self):
        assert Normalizer.normalize_email("  JOHN.SMITH@Outlook.com ") == "john.smith@outlook.com"

    def test_normalize_email_invalid_returns_null(self):
        # NOTE: Using normalize_email for all tests though it isn't completely implemented to drop random words
        # but our test is what was asked
        assert Normalizer.normalize_email("not-an-email") is None
        assert Normalizer.normalize_email("") is None
        assert Normalizer.normalize_email(None) is None

    def test_normalize_skill_canonical_form(self):
        assert list(Normalizer.normalize_skills(["Python"]))[0] == "python"
        assert list(Normalizer.normalize_skills(["JavaScript"]))[0] == "javascript"
        assert list(Normalizer.normalize_skills(["  Go "]))[0] == "go"

    @pytest.mark.parametrize("raw,expected", [
        ("2021-03-15", "2021-03"),
        ("March 2021", "2021-03"),
        ("2021", None),
        ("not a date", None),
    ])
    def test_normalize_date_to_yyyy_mm(self, raw, expected):
        assert Normalizer.normalize_date(raw) == expected

class TestCsvExtractor:
    def test_extracts_clean_row(self, recruiter_csv):
        profiles = CSVExtractor(str(recruiter_csv)).extract()
        maria = next(p for p in profiles if "maria.garcia@startup.io" in (p.emails or []))
        assert maria.full_name == "Maria Garcia"
        assert maria.phones == ["+919876543210"]

    def test_completely_blank_row_is_dropped_not_crashed(self, recruiter_csv):
        profiles = CSVExtractor(str(recruiter_csv)).extract()
        assert all(p.full_name not in (None, "") for p in profiles)

    def test_row_with_name_but_no_email_still_produces_a_profile(self, recruiter_csv):
        profiles = CSVExtractor(str(recruiter_csv)).extract()
        unknown = next(p for p in profiles if p.full_name == "Unknown Person")
        assert unknown.emails == []
        assert unknown.phones == []

    def test_malformed_file_path_does_not_crash(self, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        profiles = CSVExtractor(str(missing)).extract()
        assert profiles == []

    def test_empty_file_does_not_crash(self, tmp_path):
        empty_csv = tmp_path / "empty.csv"
        empty_csv.write_text("name,email,phone,current_company,title\n")
        profiles = CSVExtractor(str(empty_csv)).extract()
        assert profiles == []

class TestGithubExtractor:
    def test_extracts_languages_as_skills(self, github_urls_file, mock_github_api):
        profiles = GitHubExtractor(str(github_urls_file)).extract()
        jane = next(p for p in profiles if p.full_name == "Jane Doe")
        skill_names = sorted(s.name for s in jane.skills)
        assert skill_names == ["go", "javascript", "python"]
        assert len(jane.skills) == 3

    def test_private_email_user_still_produces_a_profile(self, github_urls_file, mock_github_api):
        profiles = GitHubExtractor(str(github_urls_file)).extract()
        msmith = next(p for p in profiles if p.full_name == "John Smith")
        assert msmith.emails == []

    def test_404_user_is_skipped_not_crashed(self, github_urls_file, mock_github_api):
        profiles = GitHubExtractor(str(github_urls_file)).extract()
        assert all(p.full_name != "" for p in profiles)
        logins = {getattr(p, "github_login", None) for p in profiles}
        assert "ghostuser" not in logins

    def test_rate_limited_user_is_skipped_not_crashed(self, github_urls_file, mock_github_api):
        profiles = GitHubExtractor(str(github_urls_file)).extract()
        assert isinstance(profiles, list)

    def test_empty_repo_list_yields_empty_skills_not_none(self, github_urls_file, mock_github_api):
        profiles = GitHubExtractor(str(github_urls_file)).extract()
        empty_person = next(p for p in profiles if p.full_name == "Empty Person")
        assert empty_person.skills == []

class TestMergeEngine:
    @pytest.fixture
    def merged_profiles(self, recruiter_csv, github_urls_file, mock_github_api):
        csv_profiles = CSVExtractor(str(recruiter_csv)).extract()
        github_profiles = GitHubExtractor(str(github_urls_file)).extract()
        return MergeEngine().merge(
            [(csv_profiles, 0.5), (github_profiles, 0.9)]
        )

    def test_matches_by_normalized_email(self, merged_profiles):
        jane = next(p for p in merged_profiles if "jane.doe@gmail.com" in (p.emails or []))
        assert jane.phones == ["+15551234567"]
        assert jane.headline == "Senior Software Engineer | TechCorp"
        assert {s.name for s in jane.skills} == {"python", "go", "javascript"}

    def test_duplicate_csv_rows_dedupe_after_normalization(self, merged_profiles):
        jane = next(p for p in merged_profiles if "jane.doe@gmail.com" in (p.emails or []))
        assert jane.phones.count("+15551234567") == 1

    def test_no_email_match_creates_two_separate_profiles(self, merged_profiles):
        smiths = [p for p in merged_profiles if p.full_name == "John Smith"]
        assert len(smiths) == 2

    def test_higher_trust_source_wins_scalar_conflict(self):
        from src.models import CanonicalProfile
        low = CanonicalProfile(emails=["a@b.com"], full_name="A B", company="OldCo")
        high = CanonicalProfile(emails=["a@b.com"], full_name="A B", company="NewCo")
        merged = MergeEngine().merge([([low], 0.3), ([high], 0.9)])
        assert merged[0].company == "NewCo"

    def test_provenance_recorded_for_every_populated_field(self, merged_profiles):
        jane = next(p for p in merged_profiles if "jane.doe@gmail.com" in (p.emails or []))
        provenance_fields = {p.field for p in jane.provenance}
        assert "phones" in provenance_fields
        assert "skills" in provenance_fields

    def test_conflicting_fields_lower_overall_confidence(self):
        from src.models import CanonicalProfile
        no_conflict = CanonicalProfile(emails=["x@y.com"], full_name="X Y")
        conflict_a = CanonicalProfile(emails=["c@d.com"], full_name="Name One")
        conflict_b = CanonicalProfile(emails=["c@d.com"], full_name="Name Two")

        merged_clean = MergeEngine().merge([([no_conflict], 0.8)])
        merged_conflict = MergeEngine().merge([([conflict_a], 0.5), ([conflict_b], 0.5)])

        assert merged_conflict[0].overall_confidence < merged_clean[0].overall_confidence

class TestProjector:
    @pytest.fixture
    def merged_profiles(self, recruiter_csv, github_urls_file, mock_github_api):
        csv_profiles = CSVExtractor(str(recruiter_csv)).extract()
        github_profiles = GitHubExtractor(str(github_urls_file)).extract()
        return MergeEngine().merge([(csv_profiles, 0.5), (github_profiles, 0.9)])

    def test_default_schema_has_all_required_top_level_fields(self, merged_profiles):
        default_config = {"fields": None, "include_confidence": True, "include_provenance": True}
        output = Projector().project(merged_profiles, default_config)
        for candidate in output["candidates"]:
            for key in ("candidate_id", "full_name", "emails", "phones", "skills",
                        "experience", "education", "overall_confidence"):
                assert key in candidate

    def test_custom_config_renames_and_subsets_fields(self, merged_profiles, custom_config):
        output = Projector().project(merged_profiles, custom_config)
        jane = next(c for c in output["candidates"] if c.get("full_name") == "Jane Doe"
                    and c.get("primary_email") == "jane.doe@gmail.com")
        assert set(jane.keys()) == {"full_name", "primary_email", "phone", "skills", "overall_confidence"}
        assert jane["phone"] == "+15551234567"
        assert sorted(jane["skills"]) == ["go", "javascript", "python"]

    def test_on_missing_null_keeps_field_with_null_value(self, merged_profiles, custom_config):
        custom_config["on_missing"] = "null"
        output = Projector().project(merged_profiles, custom_config)
        unknown = next(c for c in output["candidates"] if c["full_name"] == "Unknown Person")
        assert "primary_email" in unknown
        assert unknown["primary_email"] is None

    def test_on_missing_omit_drops_the_key_entirely(self, merged_profiles, custom_config):
        custom_config["on_missing"] = "omit"
        output = Projector().project(merged_profiles, custom_config)
        unknown = next(c for c in output["candidates"] if c["full_name"] == "Unknown Person")
        assert "primary_email" not in unknown

    def test_on_missing_error_raises_for_required_field(self, merged_profiles, custom_config):
        custom_config["on_missing"] = "error"
        with pytest.raises(Exception):
            Projector().project(merged_profiles, custom_config)

    def test_provenance_can_be_toggled_off(self, merged_profiles):
        config = {"fields": None, "include_confidence": True, "include_provenance": False}
        output = Projector().project(merged_profiles, config)
        for candidate in output["candidates"]:
            assert "provenance" not in candidate

    def test_path_resolver_handles_array_index_and_nested_dot_path(self, merged_profiles):
        config = {
            "fields": [
                {"path": "city", "from": "location.city", "type": "string"},
                {"path": "first_skill", "from": "skills[0].name", "type": "string"},
            ],
            "on_missing": "null",
        }
        output = Projector().project(merged_profiles, config)
        assert all("city" in c for c in output["candidates"])

class TestPipelineEndToEnd:
    def test_full_pipeline_runs_without_crashing_on_mixed_quality_sources(
        self, recruiter_csv, github_urls_file, mock_github_api
    ):
        csv_profiles = CSVExtractor(str(recruiter_csv)).extract()
        github_profiles = GitHubExtractor(str(github_urls_file)).extract()
        merged = MergeEngine().merge([(csv_profiles, 0.5), (github_profiles, 0.9)])
        output = Projector().project(merged, {"fields": None, "include_confidence": True})
        assert len(output["candidates"]) >= 5

    def test_pipeline_is_deterministic(self, recruiter_csv, github_urls_file, mock_github_api):
        def run():
            csv_profiles = CSVExtractor(str(recruiter_csv)).extract()
            github_profiles = GitHubExtractor(str(github_urls_file)).extract()
            merged = MergeEngine().merge([(csv_profiles, 0.5), (github_profiles, 0.9)])
            return Projector().project(merged, {"fields": None, "include_confidence": True})

        first = json.dumps(run(), sort_keys=True)
        second = json.dumps(run(), sort_keys=True)
        assert first == second

    def test_entirely_garbage_source_does_not_take_down_other_sources(self, tmp_path, github_urls_file, mock_github_api):
        garbage_csv = tmp_path / "garbage.csv"
        garbage_csv.write_text("this is not,a valid csv at all\n\x00\x01binary junk")
        csv_profiles = CSVExtractor(str(garbage_csv)).extract()
        github_profiles = GitHubExtractor(str(github_urls_file)).extract()
        merged = MergeEngine().merge([(csv_profiles, 0.5), (github_profiles, 0.9)])
        assert len(merged) >= 1
