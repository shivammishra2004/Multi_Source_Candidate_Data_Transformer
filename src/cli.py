import argparse
import json
import logging
import sys

from .extractors.factory import get_extractor
from .merge_engine import MergeEngine
from .projector import Projector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("--source", action='append', nargs=3, metavar=('TYPE', 'PATH', 'WEIGHT'), required=True, 
                        help="Specify extractor type, file path, and trust weight (e.g. --source csv data/ats_sample.csv 0.5)")
    parser.add_argument("--config", required=True, help="Path to the runtime config.json")
    parser.add_argument("--output", help="Path to save the output JSON (default is stdout)")
    parser.add_argument("--mapping", help="Optional JSON file mapping email addresses to GitHub URLs")
    parser.add_argument("--github-mock", help="Optional JSON file containing mock GitHub API responses")
    
    args = parser.parse_args()
    
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config {args.config}: {e}")
        sys.exit(1)
        
    mapping_data = {}
    if args.mapping:
        try:
            with open(args.mapping, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)
            logging.info(f"Loaded {len(mapping_data)} mappings from {args.mapping}")
        except Exception as e:
            logging.error(f"Failed to load mapping {args.mapping}: {e}")
            sys.exit(1)

    logging.info("Starting Ingestion & Extraction...")
    
    if args.github_mock:
        import os
        os.environ["GITHUB_MOCK_FILE"] = args.github_mock
        logging.info(f"Using mock GitHub data from {args.github_mock}")
    
    # 1. Extract dynamically
    all_extracted = []
    for src_type, path, weight in args.source:
        try:
            w = float(weight)
            extractor = get_extractor(src_type, path, w)
            
            # Inject mapping URLs into GitHubExtractor
            if src_type == "github" and mapping_data:
                if hasattr(extractor, 'additional_urls'):
                    extractor.additional_urls.extend(mapping_data.values())
                    
            profiles = extractor.extract()
            logging.info(f"Extracted {len(profiles)} profiles from {src_type} ({path}).")
            all_extracted.append((extractor.source_name, w, profiles))
            
            # Save fetched github data if this is the github source
            if src_type == "github":
                github_output_path = "fetched_github_data.json"
                try:
                    with open(github_output_path, 'w', encoding='utf-8') as f:
                        json.dump([p.to_dict() for p in profiles], f, indent=2)
                    logging.info(f"Saved fetched github data to {github_output_path}")
                except Exception as e:
                    logging.error(f"Failed to save fetched github data: {e}")
        except ValueError as e:
            logging.error(f"Failed to initialize extractor: {e}")
            sys.exit(1)
            
    # Apply Mapping
    if mapping_data:
        from .normalizer import Normalizer
        # normalize keys of mapping_data
        norm_mapping = {}
        for email, url in mapping_data.items():
            norm_email = Normalizer.normalize_email(email)
            norm_url = Normalizer.normalize_url(url)
            if norm_email and norm_url:
                norm_mapping[norm_email] = norm_url
                
        for _, _, profiles in all_extracted:
            for p in profiles:
                for email in p.emails:
                    norm_email = Normalizer.normalize_email(email)
                    if norm_email in norm_mapping:
                        p.links.github = norm_mapping[norm_email]
                        break
                        
    # 2. Merge 
    logging.info("Merging profiles...")
    merger = MergeEngine(variance_penalty=0.05)
    
    if len(all_extracted) >= 1:
        canonical_profiles = merger.merge_batch(all_extracted)
    else:
        canonical_profiles = []
        
    logging.info(f"Merged into {len(canonical_profiles)} canonical profiles.")
    
    # 3. Project
    logging.info("Applying runtime configuration projection...")
    projector = Projector(config=config_data)
    final_output = projector.project(canonical_profiles)
    
    # Output
    json_str = json.dumps(final_output, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(json_str)
        num_records = len(final_output.get("candidates", [])) if isinstance(final_output, dict) else len(final_output)
        logging.info(f"Successfully wrote {num_records} records to {args.output}")
    else:
        print(json_str)

if __name__ == "__main__":
    main()
