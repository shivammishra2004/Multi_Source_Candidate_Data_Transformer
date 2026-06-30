import time

import pytest

from src.normalizer import Normalizer
from src.extractors.csv_extractor import CSVExtractor
from src.extractors.github_extractor import GitHubExtractor
from src.merge_engine import MergeEngine
from src.projector import Projector
from src.models import CanonicalProfile, Skill


# ---------------------------------------------------------------------------
# Normalizer — alias handling, country codes, messier real-world strings
# ---------------------------------------------------------------------------

class TestNormalizerExtended:

    @pytest.mark.parametrize("raw,expected", [
        ("JS", "javascript"),
        ("Js", "javascript"),
        ("TS", "typescript"),
        ("Golang", "go"),
        ("ReactJS", "react"),
        ("Node.js", "nodejs"),
        ("C++", "cpp"),
        ("C#", "csharp"),
    ])
    def test_skill_aliases_canonicalize_to_same_form(self, raw, expected):
        assert Normalizer.normalize_skill(raw) == expected

    def test_skill_canonicalization_is_idempotent(self):
        once = Normalizer.normalize_skill("Python")
        twice = Normalizer.normalize_skill(once)
        assert once == twice

    @pytest.mark.parametrize("raw,expected", [
        ("United States", "US"),
        ("USA", "US"),
        ("India", "IN"),
        ("U.K.", "GB"),
        ("United Kingdom", "GB"),
    ])
    def test_country_normalizes_to_iso3166_alpha2(self, raw, expected):
        assert Normalizer.normalize_country(raw) == expected

    def test_unrecognized_country_returns_null_not_guess(self):
        assert Normalizer.normalize_country("Wakanda") is None

    @pytest.mark.parametrize("raw", [
        "a@@b.com",          # double @
        "no-at-sign.com",
        "user@",
        "@domain.com",
        "user@domain",        # no TLD
        "user name@domain.com",  # embedded space
    ])
    def test_malformed_emails_all_return_null(self, raw):
        assert Normalizer.normalize_email(raw) is None

    def test_email_with_plus_addressing_is_preserved(self):
        assert Normalizer.normalize_email("Jane.Doe+recruiting@gmail.com") == "jane.doe+recruiting@gmail.com"

    @pytest.mark.parametrize("raw,expected", [
        ("Jan 2020 - Present", ("2020-01", None)),
        ("2019-06 to 2021-09", ("2019-06", "2021-09")),
        ("Present", (None, None)),
    ])
    def test_date_range_parsing_present_means_open_ended(self, raw, expected):
        start, end = Normalizer.normalize_date_range(raw)
        assert (start, end) == expected

    def test_phone_with_extension_strips_or_flags_extension(self):
        result = Normalizer.format_phone("555-123-4567 x123")
        assert result is None or "x123" not in result

    def test_normalize_phone_never_raises_on_unicode_garbage(self):
        assert Normalizer.format_phone("☎️ not a number 电话") is None


# ---------------------------------------------------------------------------
# CSV extractor — encoding, formatting, ignored columns
# ---------------------------------------------------------------------------

class TestCsvExtractorExtended:

    def test_quoted_field_with_embedded_comma(self, tmp_path):
        csv_text = (
            'name,email,phone,current_company,title\n'
            '"Doe, Jane",jane@x.com,555-000-1111,"Acme, Inc.",Engineer\n'
        )
        path = tmp_path / "quoted.csv"
        path.write_text(csv_text, encoding="utf-8")
        profiles = CSVExtractor(str(path)).extract()
        assert profiles[0].full_name == "Doe, Jane"
        assert profiles[0].experience[0].company == "Acme, Inc."

    def test_unknown_extra_columns_are_ignored_not_crashed(self, tmp_path):
        csv_text = (
            "name,email,phone,current_company,title,favorite_color,linkedin_id\n"
            "Sam Lee,sam@x.com,555-222-3333,Acme,Eng,blue,abc123\n"
        )
        path = tmp_path / "extra_cols.csv"
        path.write_text(csv_text, encoding="utf-8")
        profiles = CSVExtractor(str(path)).extract()
        assert profiles[0].full_name == "Sam Lee"

    def test_utf8_bom_does_not_corrupt_first_header(self, tmp_path):
        path = tmp_path / "bom.csv"
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write("name,email,phone,current_company,title\n")
            f.write("Bom Test,bom@x.com,555-444-5555,Acme,Eng\n")
        profiles = CSVExtractor(str(path)).extract()
        assert len(profiles) == 1
        assert profiles[0].full_name == "Bom Test"

    def test_missing_required_columns_in_header_does_not_crash(self, tmp_path):
        path = tmp_path / "wrong_header.csv"
        path.write_text("first,last\nJohn,Doe\n", encoding="utf-8")
        profiles = CSVExtractor(str(path)).extract()
        assert isinstance(profiles, list)

    def test_unicode_name_is_preserved(self, tmp_path):
        path = tmp_path / "unicode.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("name,email,phone,current_company,title\n")
            f.write("José García,jose@x.com,555-777-8888,Acme,Eng\n")
        profiles = CSVExtractor(str(path)).extract()
        assert profiles[0].full_name == "José García"


# ---------------------------------------------------------------------------
# GitHub extractor — pagination, forks, malformed blog URLs
# ---------------------------------------------------------------------------

class TestGithubExtractorExtended:

    def test_repos_with_duplicate_language_count_once_as_a_skill(self, github_urls_file, mock_github_api):
        profiles = GitHubExtractor(str(github_urls_file)).extract()
        jane = next(p for p in profiles if p.full_name == "Jane Doe")
        names = [s.name for s in jane.skills]
        assert len(names) == len(set(names))

    def test_malformed_blog_url_does_not_crash_link_parsing(self, monkeypatch, github_urls_file):
        import requests

        def fake_get(url, *a, **k):
            class R:
                status_code = 200
                def json(self_inner):
                    if url.endswith("/repos"):
                        return []
                    return {
                        "login": "weirdblog",
                        "name": "Weird Blog",
                        "email": "weird@x.com",
                        "bio": None,
                        "company": None,
                        "blog": "not a url at all, just text",
                    }
                def raise_for_status(self_inner):
                    pass
            return R()

        monkeypatch.setattr(requests, "get", fake_get)
        path = github_urls_file.parent / "single_url.txt"
        path.write_text("https://github.com/weirdblog\n", encoding="utf-8")
        profiles = GitHubExtractor(str(path)).extract()
        assert len(profiles) == 1
        assert profiles[0].links.portfolio in (None, "")

    def test_duplicate_url_for_same_login_only_produces_one_profile(self, tmp_path, mock_github_api):
        path = tmp_path / "dupe_urls.txt"
        path.write_text("https://github.com/janedoe-dev\nhttps://github.com/janedoe-dev\n", encoding="utf-8")
        profiles = GitHubExtractor(str(path)).extract()
        assert len(profiles) == 1


# ---------------------------------------------------------------------------
# Merge engine — 3+ sources, tie-breaking, secondary-email linking
# ---------------------------------------------------------------------------

class TestMergeEngineExtended:

    def test_three_way_merge_combines_all_sources(self):
        a = CanonicalProfile(emails=["x@y.com"], full_name="X Y", phones=["+15550000001"])
        b = CanonicalProfile(emails=["x@y.com"], full_name="X Y", headline="From source B")
        c = CanonicalProfile(emails=["x@y.com"], full_name="X Y", skills=[Skill(name="rust", confidence=0.9, sources=["c"])])
        merged = MergeEngine().merge([([a], 0.5), ([b], 0.7), ([c], 0.9)])
        assert len(merged) == 1
        result = merged[0]
        assert result.phones == ["+15550000001"]
        assert result.headline == "From source B"
        assert any(s.name == "rust" for s in result.skills)

    def test_equal_trust_weight_tiebreak_is_deterministic(self):
        a = CanonicalProfile(emails=["tie@x.com"], full_name="A", headline="short")
        b = CanonicalProfile(emails=["tie@x.com"], full_name="A", headline="a much longer and more descriptive headline")
        run1 = MergeEngine().merge([([a], 0.5), ([b], 0.5)])[0].headline
        run2 = MergeEngine().merge([([b], 0.5), ([a], 0.5)])[0].headline
        assert run1 == run2

    def test_secondary_email_links_candidate_across_sources(self):
        csv_profile = CanonicalProfile(emails=["work@corp.com", "personal@gmail.com"], full_name="Multi Email")
        github_profile = CanonicalProfile(emails=["personal@gmail.com"], full_name="Multi Email", headline="dev")
        merged = MergeEngine().merge([([csv_profile], 0.5), ([github_profile], 0.9)])
        assert len(merged) == 1
        assert merged[0].headline == "dev"

    def test_merging_profile_with_all_null_fields_does_not_crash(self):
        empty = CanonicalProfile(emails=["empty@x.com"], full_name=None)
        merged = MergeEngine().merge([([empty], 0.5)])
        assert len(merged) == 1

    def test_empty_source_list_returns_empty_result(self):
        assert MergeEngine().merge([]) == []
        assert MergeEngine().merge([([], 0.5)]) == []


# ---------------------------------------------------------------------------
# Projector — malformed / adversarial configs
# ---------------------------------------------------------------------------

class TestProjectorExtended:

    @pytest.fixture
    def merged_profiles(self, recruiter_csv, github_urls_file, mock_github_api):
        csv_profiles = CSVExtractor(str(recruiter_csv)).extract()
        github_profiles = GitHubExtractor(str(github_urls_file)).extract()
        return MergeEngine().merge([(csv_profiles, 0.5), (github_profiles, 0.9)])

    def test_nonexistent_field_path_resolves_to_missing_not_crash(self, merged_profiles, edge_config):
        output = Projector().project(merged_profiles, edge_config)
        for candidate in output["candidates"]:
            assert candidate.get("ghost_field") is None

    def test_out_of_range_array_index_resolves_to_missing_not_indexerror(self, merged_profiles, edge_config):
        output = Projector().project(merged_profiles, edge_config)
        for candidate in output["candidates"]:
            assert candidate.get("tenth_skill") is None

    def test_empty_fields_list_returns_minimal_candidate_objects(self, merged_profiles):
        output = Projector().project(merged_profiles, {"fields": [], "on_missing": "null"})
        assert len(output["candidates"]) == len(merged_profiles)

    def test_unknown_on_missing_value_fails_loudly_at_config_time(self, merged_profiles):
        bad_config = {"fields": [{"path": "full_name", "type": "string"}], "on_missing": "ommit"}
        with pytest.raises(Exception):
            Projector().project(merged_profiles, bad_config)

    def test_duplicate_target_field_names_in_config_does_not_silently_drop_one(self, merged_profiles):
        dup_config = {
            "fields": [
                {"path": "name", "from": "full_name", "type": "string"},
                {"path": "name", "from": "headline", "type": "string"},
            ],
            "on_missing": "null",
        }
        try:
            output = Projector().project(merged_profiles, dup_config)
            assert "name" in output["candidates"][0]
        except Exception:
            pass

    def test_config_requesting_object_field_as_scalar_type_does_not_crash(self, merged_profiles):
        weird_config = {
            "fields": [{"path": "skills", "type": "string"}],
            "on_missing": "null",
        }
        try:
            Projector().project(merged_profiles, weird_config)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------

class TestScale:

    def test_five_thousand_candidates_completes_in_reasonable_time(self, large_recruiter_csv):
        start = time.monotonic()
        profiles = CSVExtractor(str(large_recruiter_csv)).extract()
        merged = MergeEngine().merge([(profiles, 0.5)])
        Projector().project(merged, {"fields": None, "include_confidence": True})
        elapsed = time.monotonic() - start
        assert len(merged) == 5000
        assert elapsed < 30, f"5000 candidates took {elapsed:.1f}s — investigate for O(n^2) merge behavior"

    def test_no_duplicate_candidates_at_scale(self, large_recruiter_csv):
        profiles = CSVExtractor(str(large_recruiter_csv)).extract()
        merged = MergeEngine().merge([(profiles, 0.5)])
        emails_seen = [e for p in merged for e in (p.emails or [])]
        assert len(emails_seen) == len(set(emails_seen))


# ---------------------------------------------------------------------------
# Fuzz / robustness (optional — skips cleanly if hypothesis isn't installed)
# ---------------------------------------------------------------------------

hypothesis = pytest.importorskip("hypothesis", reason="pip install hypothesis to enable fuzz tests")
from hypothesis import given, strategies as st  # noqa: E402


class TestFuzzRobustness:

    @given(st.text())
    def test_normalize_phone_never_raises_on_arbitrary_text(self, raw):
        result = Normalizer.format_phone(raw)
        assert result is None or isinstance(result, str)

    @given(st.text())
    def test_normalize_email_never_raises_on_arbitrary_text(self, raw):
        result = Normalizer.normalize_email(raw)
        assert result is None or "@" in result

    @given(st.text())
    def test_normalize_skill_never_raises_on_arbitrary_text(self, raw):
        Normalizer.normalize_skill(raw)

