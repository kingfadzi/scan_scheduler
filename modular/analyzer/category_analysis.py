from modular.shared.models import Session, Dependency
from config.config import Config
from modular.shared.base_logger import BaseLogger
import pandas as pd
import re
import yaml
import time
import logging
import os
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
            # Flatten rules: if subcategories exist, use them; otherwise use an empty sub_category.
            compiled_list = []
            for cat in rules.get('categories', []):
                if 'subcategories' in cat:
                    for sub in cat['subcategories']:
                        for pattern in sub.get('patterns', []):
                            compiled_list.append((re.compile(pattern, re.IGNORECASE), cat['name'], sub.get('name', "")))
                else:
                    for pattern in cat.get('patterns', []):
                        compiled_list.append((re.compile(pattern, re.IGNORECASE), cat['name'], ""))
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
        return compiled_rules_cache[rule_file]

    def categorize_row(self, row):
        rules = self.get_compiled_rules(row['package_type'])
        for regex, top_cat, sub_cat in rules:
            if regex.search(row['name']):
                return pd.Series({"category": top_cat, "sub_category": sub_cat})
        return pd.Series({"category": "Other", "sub_category": ""})

    def process_data(self):
        self.logger.info("Starting data processing...")
        query = """
            SELECT d.id, d.repo_id, d.name, d.version, d.package_type, 
                   b.tool, b.tool_version, b.runtime_version
            FROM dependencies d 
            LEFT JOIN build_tools b ON d.repo_id = b.repo_id
            WHERE d.package_type IS NOT NULL
        """
        start_time = time.time()
        total_rows = 0

        with Session() as session:
            session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
            session.commit()

            for chunk_idx, chunk in enumerate(pd.read_sql(query, con=session.connection(), chunksize=CHUNK_SIZE)):
                if chunk.empty:
                    self.logger.warning(f"Chunk {chunk_idx+1} returned no rows.")
                    continue
                self.logger.info(f"Processing chunk {chunk_idx+1} (size: {len(chunk)})...")
                chunk_start = time.time()
                # Apply categorization row-wise
                cat_values = chunk.apply(self.categorize_row, axis=1)
                chunk["category"] = cat_values["category"]
                chunk["sub_category"] = cat_values["sub_category"]
                updates = chunk[['id', 'category', 'sub_category']].to_dict(orient='records')
                if updates:
                    session.bulk_update_mappings(Dependency, updates)
                    session.commit()
                self.logger.info(f"Chunk {chunk_idx+1} processed in {time.time() - chunk_start:.2f} seconds")
                total_rows += len(chunk)

            session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
            session.commit()

        total_duration = time.time() - start_time
        self.logger.info(f"Processing complete: {total_rows} rows processed in {total_duration:.2f} seconds")
        print("Processing complete. Materialized view updated.")

if __name__ == '__main__':
    categorizer = DependencyCategorizer()
    categorizer.process_data()