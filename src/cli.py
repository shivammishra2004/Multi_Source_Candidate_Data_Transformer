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
    
    args = parser.parse_args()
    
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config {args.config}: {e}")
        sys.exit(1)

    logging.info("Starting Ingestion & Extraction...")
    
    # 1. Extract dynamically
    all_extracted = []
    for src_type, path, weight in args.source:
        try:
            w = float(weight)
            extractor = get_extractor(src_type, path, w)
            profiles = extractor.extract()
            logging.info(f"Extracted {len(profiles)} profiles from {src_type} ({path}).")
            all_extracted.append((extractor.source_name, w, profiles))
        except ValueError as e:
            logging.error(f"Failed to initialize extractor: {e}")
            sys.exit(1)
            
    # 2. Merge 
    # For backward compatibility with the existing MergeEngine.merge_batch, 
    # we'll assume the first two sources are github and csv if present. 
    # To truly support N sources, MergeEngine would need an update, 
    # but for now we fold them using the existing logic if there are 2.
    logging.info("Merging profiles...")
    merger = MergeEngine(variance_penalty=0.05)
    
    if len(all_extracted) >= 2:
        # Map them back for the old merge_batch signature temporarily
        src1, w1, profs1 = all_extracted[0]
        src2, w2, profs2 = all_extracted[1]
        canonical_profiles = merger.merge_batch(profs1, profs2, github_weight=w1, csv_weight=w2)
        # Note: if there are >2 sources, they are currently ignored by the old merge_batch.
        if len(all_extracted) > 2:
            logging.warning("MergeEngine currently only merges the first 2 sources.")
    elif len(all_extracted) == 1:
        canonical_profiles = all_extracted[0][2]
    else:
        canonical_profiles = []
        
    logging.info(f"Merged into {len(canonical_profiles)} canonical profiles.")
    
    # 3. Project
    logging.info("Applying runtime configuration projection...")
    projector = Projector(config=config_data)
    final_output = projector.project_batch(canonical_profiles)
    
    # Output
    json_str = json.dumps(final_output, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(json_str)
        logging.info(f"Successfully wrote {len(final_output)} records to {args.output}")
    else:
        print(json_str)

if __name__ == "__main__":
    main()
