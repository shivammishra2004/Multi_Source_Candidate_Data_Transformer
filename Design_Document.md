# Multi-Source Candidate Data Transformer
**Technical Design Document**

## 1. The Problem
Candidate data arrives from multiple fragmented sources (CSVs, ATS JSONs, GitHub APIs, etc.) with conflicting formats, missing values, and varying degrees of reliability. Downstream systems require a single, trustworthy canonical profile. A "wrong-but-confident" merge can silently pollute hiring decisions. The goal is to build a highly deterministic, batch-processing transformer that ingests, sanitizes, merges, and dynamically projects these records into a clean, traceable schema based on runtime configuration.

## 2. Pipeline / Step Breakdown
Our pipeline follows a strict separation of concerns via a 4-stage engine:
1. **Ingest & Extract**: Standardized adapter interfaces (`CSVExtractor`, `GitHubAPIExtractor`) pull raw data. Unstructured API calls are parallelized using `ThreadPoolExecutor` with built-in rate-limit handling.
2. **Stateless Normalization**: Applies strict formatting rules (e.g., casing, stripping, E.164 conversion) to fields *before* the merge process to guarantee accurate identity matching.
3. **Deterministic Merge Engine**: Records are grouped into buckets using a strict exact-match on primary keys (Normalized Email or GitHub URL). It combines buckets into single canonical profiles using predefined Source Trust Weights, string-length tie-breakers, and Set Unions. Calculates overall confidence and attaches granular provenance.
4. **Dynamic Projector**: A decoupled output layer that applies the `runtime_config`. It extracts nested paths, applies per-field normalizations/type-casting dynamically, handles missing data policies, and strips or includes metadata (confidence, provenance).

## 3. Canonical Output Schema & Normalized Formats
The internal state maintains a highly structured schema regardless of the final requested output.
*   **Canonical Schema**: `candidate_id` (str), `full_name` (str), `emails` (str[]), `phones` (str[]), `location` (dict), `links` (dict), `headline` (str), `company` (str), `years_experience` (float), `skills` (list of dicts with name, confidence, sources), `experience`/`education` (lists of dicts), `provenance` (list of dicts), `overall_confidence` (float).
*   **Emails**: Lowercased and whitespace-trimmed. Used as the primary identity key.
*   **Phones**: Coerced to **E.164 Format** (e.g., `+14155550198`) via the `phonenumbers` library. Invalid extensions are dropped; numbers without a country code default to US parsing.
*   **Skills**: Canonicalized to lowercase, stripped of trailing spaces, and deduplicated into Sets.
*   **Dates**: Parsed and coerced to ISO-8601 subset `YYYY-MM`.
*   **URLs (e.g., GitHub, LinkedIn)**: Stripped of schema (`http://`, `https://`), `www.`, and trailing slashes.
*   **Names**: Stripped of leading/trailing whitespace, and multiple inner spaces are collapsed to a single space.

## 4. Merge / Conflict-Resolution Policy & Confidence
The engine operates entirely on deterministic logic to prevent probabilistic data pollution.
*   **Identity Matching**: Records are grouped exactly by their normalized email address. If no email exists, GitHub URLs act as a secondary fallback key.
*   **Scalar Conflicts (Strings, Numbers, Objects like Location)**: Governed by **Source Trust Weights** (e.g., GitHub API = 0.9, CSV = 0.5). In a conflict, the highest weight wins. For string fields, the tie-breaker is string length (favoring the more detailed value).
*   **Array Conflicts (Emails, Phones, Skills, Links)**: Handled via **Set Union**. Values from all sources are merged comprehensively and deduplicated using their normalized formats. Skill objects track all sources they were found in.
*   **Confidence & Provenance Assignment**: Every field generates a `Provenance` record detailing its source, extraction method, and confidence. `overall_confidence` is a weighted average of merged fields, explicitly penalized by a **Variance Modifier** (e.g., `-0.05` per conflict) if sources disagreed. Standalone fields simply inherit their source's trust weight.

## 5. Runtime Custom-Output Config (Projection & Validation)
The Projector runs at the very end of the pipeline, completely isolated from the Merge Engine.
*   **Path Resolution**: Uses a custom deep-get utility to map canonical paths (e.g., `emails[0]`, `location.city`, `skills[].name`) to requested output keys (e.g., `primary_email`).
*   **Type Validation**: Intercepts `type` directives (`string`, `number`, `string[]`) to dynamically cast values.
*   **Per-Field Normalization**: Intercepts `normalize: "E164"` or `normalize: "canonical"` directives to format values just prior to serialization.
*   **Missing Data Policy**: Governed by `on_missing`:
    *   `null`: Outputs the key with a `null` value.
    *   `omit`: Drops the key entirely from the JSON object.
    *   `error`: If `required=True`, throws a `ValueError` aborting the projection for that field. Otherwise, falls back to `null` or `omit` as requested.
*   **Metadata Toggles**: Respects `include_confidence` and `include_provenance` flags to strip or include metadata from the final JSON payload.

## 6. Edge Cases & Scope Boundaries
**Handled Edge Cases:**
1.  **Missing Primary Keys**: If an email is missing (e.g., a private GitHub profile) and no GitHub URL matches, the engine deterministically treats the profile as a **standalone, unmerged record**. It does not risk a false-positive merge based on a common name.
2.  **Different Emails for the Same Person**: If a CSV has `work@gmail.com` and GitHub has `personal@gmail.com`, they are treated as two separate people unless a manual mapping file is provided. This enforces the strict "deterministic" constraint.
3.  **Invalid/Partial Phone Numbers**: If a phone number is provided without a country code, the normalizer defaults to parsing it as a US region number. If it cannot be parsed into a possible number, it is safely skipped rather than crashing the pipeline.
4.  **Type Mismatches on Projection**: If a field is present but fails type casting (e.g., expecting a number but receiving un-castable text) and `on_missing="error"` with `required=True`, it throws a strict validation error. If not required, it treats the value as missing and applies the missing policy.
5.  **GitHub API Not Found (404s) / Rate Limits**: If a provided GitHub URL results in a 404 Not Found (or if strict rate limits are hit), the extractor gracefully handles the failure. It logs a warning, yields an empty profile list for that URL, and allows the batch pipeline to proceed uninterrupted.

**Deliberately Descoped (Under Time Pressure):**
1.
2.  **Automated Web Scraping for Missing URLs**: We deliberately omitted falling back to a web scraper (e.g., searching Google/LinkedIn for a candidate's name) when a GitHub profile is missing or 404s.
3.  **Live Phone Validation & Region Guessing**: While we format numbers to E.164 locally using the `phonenumbers` library, we descoped making live API calls (e.g., via Twilio) to verify if the number is currently active.








**Fuzzy String Matching (Jaro-Winkler/Levenshtein)**: For names or companies. Introduces probabilistic failure points that violate the deterministic "wrong-but-confident" constraint.
**NLP/LLM Resume Parsing**: Extracting data from unstructured prose (PDF/DOCX) using AI was omitted to guarantee 100% explainable, repeatable batch runs.