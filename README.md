# Multi-Source Candidate Data Transformer

A deterministic, rule-based data pipeline that ingests messy candidate data from multiple sources (Structured CSV & Unstructured GitHub API), normalizes it, resolves conflicts, and outputs a single canonical JSON profile based on a dynamic runtime configuration.

## Prerequisites

- **Python 3.8+**
- The project relies on standard libraries and a few external packages (`requests` for API calls, `phonenumbers` for E.164 conversion, and `python-dotenv`).

```bash
pip install requests phonenumbers python-dotenv
```

## Configuration (Environment Variables)

To avoid aggressive rate-limiting by the GitHub API when not using mock data, you should configure a GitHub Personal Access Token.

1. Create a `.env` file in the root of the project.
2. Add your token to the file:
```env
GITHUB_TOKEN=your_personal_access_token_here
```
The `python-dotenv` package will automatically load this token when the pipeline runs.

## How to Run the Pipeline

The pipeline is executed via a Command Line Interface (CLI). You must run the tool as a Python module from the root directory of the project.

### Basic Usage

```bash
python -m src.cli \
  --source csv data/ats_sample.csv 0.5 \
  --source github data/urls.txt 0.9 \
  --config data/runtime_config.json \
  --output final_profiles.json
```

### CLI Arguments

- `--source`: Specify a data source. This argument can be repeated multiple times. It takes three parameters:
  1. **Extractor Type** (e.g., `csv`, `github`)
  2. **File Path**
  3. **Trust Weight** (e.g., `0.5`, `0.9`)
- `--config`: *(Required)* Path to the runtime `config.json` file which dictates the shape of the final output.
- `--output`: *(Optional)* Path to save the final JSON output. If omitted, the JSON will print to standard output (`stdout`).
- `--mapping`: *(Optional)* Path to a JSON file mapping email addresses to GitHub profile URLs. Useful when emails in the CSV differ from the GitHub profile.
- `--github-mock`: *(Optional)* Path to a JSON file containing mock GitHub API responses to safely bypass rate limits and ensure deterministic testing.

### Advanced Usage (with Mock API and Mapping)

To test the GitHub API offline or without hitting rate limits, provide the mock JSON file and the mapping file:

```bash
python -m src.cli \
  --source csv data/ats_sample.csv 0.5 \
  --source github Data/urls.text 0.9 \
  --config data/runtime_config.json \
  --github-mock data/github_api_mocks.json \
  --mapping data/github_mapping.json \
  --output final_profiles.json
```

## Runtime Configuration (`config.json`)

The output format is entirely decoupled from the internal engine via a Dynamic Projector. The runtime config allows you to reshape the canonical profile on the fly without changing the underlying Python code.

**Key Features:**
- **Path Resolution:** Remap fields using deep nested paths (e.g., mapping `"from": "emails[0]"` to a new `"path": "primary_email"`).
- **Per-Field Normalization:** Use `"normalize": "E164"` for phones or `"normalize": "canonical"` for skills. The projector will dynamically format these on projection.
- **Type Validation:** Specify a data type (e.g., `"type": "string"` or `"type": "number"`). The projector will attempt to cast the data or safely fallback to missing policies if it fails.
- **Missing Data Policies:** Use `"on_missing": "null" | "omit" | "error"` to decide how absent data is treated globally or strictly per-field.
- **Metadata Toggles:** Turn `include_provenance` or `include_confidence` on or off globally.

## Architecture Overview

1. **Extractors (Adapter Pattern)**: Reads from CSV and GitHub API (concurrently via `ThreadPoolExecutor`). Handles missing data gracefully without crashing.
2. **Normalizer**: A stateless utility class enforcing strict formatting (E.164 for phones, `YYYY-MM` for dates).
3. **Merge Engine**: Groups records by exact-match email keys. Uses predefined Source Trust Weights to resolve scalar conflicts and Set Unions for lists. Calculates an `overall_confidence` penalized by statistical variance.
4. **Projector**: Dynamically reshapes the canonical profile into the final JSON payload based on the runtime config rules, executing real-time normalization and type-casting.
