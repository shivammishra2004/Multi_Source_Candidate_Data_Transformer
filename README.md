# Multi-Source Candidate Data Transformer

A deterministic, rule-based data pipeline that ingests messy candidate data from multiple sources (Structured CSV & Unstructured GitHub API), normalizes it, resolves conflicts, and outputs a single canonical JSON profile based on a dynamic runtime configuration.

## Prerequisites

- **Python 3.8+**
- Standard libraries are used for everything except network calls. You only need to install `requests`.

```bash
pip install requests
```

## How to Run the Pipeline

The pipeline is executed via a Command Line Interface (CLI) utilizing Python's `argparse`. You must run the tool as a Python module from the root directory of the project.

### Basic Usage

```bash
python -m src.cli --source csv data/ats_sample.csv 0.5 --source github data/urls.txt 0.9 --config data/runtime_config.json
```

### Arguments

- `--source`: Specify a data source. This argument can be repeated multiple times. It takes three parameters:
  1. **Extractor Type** (e.g., `csv`, `github`)
  2. **File Path**
  3. **Trust Weight** (e.g., `0.5`, `0.9`)
- `--config`: Path to the runtime `config.json` file which dictates the shape of the final output.
- `--output` *(optional)*: Path to save the final JSON output. If omitted, the JSON will print to standard output (`stdout`).

### Example with Output File

```bash
python -m src.cli --source csv data/ats_sample.csv 0.5 --source github data/urls.txt 0.9 --config data/runtime_config.json --output final_profiles.json
```


## Architecture Overview

1. **Extractors (Adapter Pattern)**: Reads from CSV and GitHub API (concurrently). Greedy extraction ensures missing data doesn't crash the row.
2. **Normalizer**: A stateless class enforcing a "Good Enough" Regex strategy to standardize phones (E.164), emails, and skills.
3. **Merge Engine**: Merges based on exact-match email keys. Uses predefined Source Trust Weights for scalars and Set Unions for lists. Implements a Statistical Variance Penalty for conflicting data.
4. **Projector**: Dynamically reshapes the canonical profile into the final JSON payload based on the `config.json` rules, handling missing data gracefully.
