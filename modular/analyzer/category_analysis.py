import pandas as pd
import re
import yaml
import time
import logging
import os
from modular.shared.models import Session
from config.config import Config
from modular.shared.base_logger import BaseLogger
from sqlalchemy import text

CHUNK_SIZE = 50000
MATERIALIZED_VIEW = "categorized_dependencies_mv"
RULES_PATH = Config.CATEGORY_RULES_PATH

RULES_MAPPING = {
    "pip": "rules_python.yaml",
    "maven": "rules_java.yaml",
    "gradle": "rules_java.yaml",
    "npm": "rules_javascript.yaml",
    "yarn": "rules_javascript.yaml",
    "go": "rules_go.yaml"
}

compiled_rules_cache = {}

class DependencyCategorizer(BaseLogger):
    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("DependencyCategorizer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    def load_rules(self, rule_file):
        rule_path = os.path.join(RULES_PATH, rule_file)
        try:
            with open(rule_path, 'r') as f:
                rules = yaml.safe_load(f)
            compiled_list = [
                (re.compile(pattern, re.IGNORECASE), cat['name'], sub.get('name', ""))
                for cat in rules.get('categories', [])
                for sub in cat.get('subcategories', [{"name": ""}])
                for pattern in sub.get('patterns', cat.get('patterns', []))
            ]
            self.logger.info(f"Loaded {len(compiled_list)} rules from {rule_path}")
            return compiled_list
        except Exception as e:
            self.logger.error(f"Error loading {rule_path}: {e}")
            return []

    def get_compiled_rules(self, package_type):
        rule_file = RULES_MAPPING.get(package_type.lower())
        if not rule_file:
            self.logger.warning(f"No rule file mapped for package type: {package_type}")
            return []
        if rule_file not in compiled_rules_cache:
            compiled_rules_cache[rule_file] = self.load_rules(rule_file)
        rules = compiled_rules_cache[rule_file]
        self.logger.info(f"Using {len(rules)} compiled rules for package type {package_type} from {rule_file}")
        return rules

    def apply_categorization(self, df):
        start_time = time.time()
        df["category"], df["sub_category"] = "Other", ""
        
        # Process each package type separately.
        package_types = df["package_type"].unique()
        for pkg_type in package_types:
            self.logger.debug(f"Processing package type: {pkg_type}")
            group = df.loc[df["package_type"] == pkg_type]
            sample_names = group["name"].head(5).tolist()
            self.logger.debug(f"Sample dependency names for {pkg_type}: {sample_names}")
            
            compiled_rules = self.get_compiled_rules(pkg_type)
            if not compiled_rules:
                self.logger.warning(f"No compiled rules for package type: {pkg_type}")
                continue

            regex_patterns, categories, sub_categories = zip(*compiled_rules)
            full_regex = "|".join(f"({pattern.pattern})" for pattern in regex_patterns)
            matches = group["name"].str.extract(full_regex, expand=False)
            
            for i, col in enumerate(matches.columns):
                matched_rows = matches[col].notna()
                num_matches = matched_rows.sum()
                self.logger.debug(f"Regex {i}: found {num_matches} matches for package type {pkg_type}")
                if num_matches > 0:
                    # Update only for rows in the group that are still "Other"
                    indices = group.index[matched_rows & (group["category"] == "Other")]
                    df.loc[indices, ["category", "sub_category"]] = (categories[i], sub_categories[i])
        
        duration = time.time() - start_time
        self.logger.info(f"Categorization completed for {len(df)} rows in {duration:.2f} seconds")
        return df

    def process_data(self):
        self.logger.info("Starting data processing...")
        query = """
            SELECT d.repo_id, d.name, d.version, d.package_type, 
                   b.tool, b.tool_version, b.runtime_version
            FROM dependencies d 
            LEFT JOIN build_tools b ON d.repo_id = b.repo_id
            WHERE d.package_type IS NOT NULL
        """
        start_time = time.time()
        with Session() as session:
            self.logger.info("Refreshing materialized view before processing...")
            session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
            session.commit()
            
            for chunk_idx, chunk in enumerate(pd.read_sql(query, con=session.connection(), chunksize=CHUNK_SIZE)):
                if chunk.empty:
                    self.logger.warning(f"Chunk {chunk_idx + 1} returned no rows.")
                    continue
                self.logger.info(f"Processing chunk {chunk_idx + 1} (size: {len(chunk)})...")
                chunk_start_time = time.time()
                chunk = self.apply_categorization(chunk)
                chunk_duration = time.time() - chunk_start_time
                self.logger.info(f"Chunk {chunk_idx + 1} processed in {chunk_duration:.2f} seconds")
            
            self.logger.info("Final refresh of materialized view...")
            session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
            session.commit()
        
        total_duration = time.time() - start_time
        self.logger.info(f"Processing complete in {total_duration:.2f} seconds.")
        print("Processing complete. Materialized view updated.")

if __name__ == '__main__':
    categorizer = DependencyCategorizer()
    categorizer.process_data()