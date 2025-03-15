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
from psycopg2.extras import execute_values

CHUNK_SIZE = 50000
MATERIALIZED_VIEW = "categorized_dependencies_mv"
RULES_PATH = Config.CATEGORY_RULES_PATH

RULES_MAPPING = {
    "pip": "python",
    "maven": "java",
    "gradle": "java",
    "npm": "javascript",
    "yarn": "javascript",
    "go": "go"
}

compiled_rules_cache = {}

class CategoryAnalyzer(BaseLogger):
    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("CategoryAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    def run_analysis(self):
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
            # Refresh materialized view before starting
            session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
            session.commit()

            # Process data in chunks
            for chunk_idx, chunk in enumerate(pd.read_sql(query, con=session.connection(), chunksize=CHUNK_SIZE)):
                if chunk.empty:
                    self.logger.warning(f"Chunk {chunk_idx+1} returned no rows.")
                    continue

                self.logger.info(f"Processing chunk {chunk_idx+1} (size: {len(chunk)})...")
                chunk_start = time.time()

                cat_values = chunk.apply(self.categorize_row, axis=1)
                chunk["category"] = cat_values["category"]
                chunk["sub_category"] = cat_values["sub_category"]

                updates = chunk[["id", "category", "sub_category"]].to_dict(orient="records")
                if updates:
                    self.bulk_update_dependencies(session.connection(), updates)

                self.logger.info(f"Chunk {chunk_idx+1} processed in {time.time() - chunk_start:.2f} seconds")
                total_rows += len(chunk)

            session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
            session.commit()

        total_duration = time.time() - start_time
        self.logger.info(f"Processing complete: {total_rows} rows processed in {total_duration:.2f} seconds")
        print("Processing complete. Materialized view updated.")

    def load_rules(self, rule_path_component):
        full_path = os.path.join(RULES_PATH, rule_path_component)
        compiled_list = []

        if os.path.isdir(full_path):
            # If it's a directory, iterate over all YAML files
            for file_name in os.listdir(full_path):
                if file_name.endswith((".yaml", ".yml")):
                    file_path = os.path.join(full_path, file_name)
                    self.logger.info(f"Loading rules from {file_path}")
                    try:
                        with open(file_path, 'r') as f:
                            rules = yaml.safe_load(f)
                        for cat in rules.get('categories', []):
                            if 'subcategories' in cat:
                                for sub in cat['subcategories']:
                                    for pattern in sub.get('patterns', []):
                                        compiled_list.append((re.compile(pattern, re.IGNORECASE), cat['name'], sub.get('name', "")))
                            else:
                                for pattern in cat.get('patterns', []):
                                    compiled_list.append((re.compile(pattern, re.IGNORECASE), cat['name'], ""))
                    except Exception as e:
                        self.logger.error(f"Error loading {file_path}: {e}")
        else:
            # Fallback: treat as a single file
            try:
                with open(full_path, 'r') as f:
                    rules = yaml.safe_load(f)
                for cat in rules.get('categories', []):
                    if 'subcategories' in cat:
                        for sub in cat['subcategories']:
                            for pattern in sub.get('patterns', []):
                                compiled_list.append((re.compile(pattern, re.IGNORECASE), cat['name'], sub.get('name', "")))
                    else:
                        for pattern in cat.get('patterns', []):
                            compiled_list.append((re.compile(pattern, re.IGNORECASE), cat['name'], ""))
            except Exception as e:
                self.logger.error(f"Error loading {full_path}: {e}")

        self.logger.info(f"Loaded {len(compiled_list)} rules from {full_path}")
        return compiled_list

    def get_compiled_rules(self, package_type):
        rule_path_component = RULES_MAPPING.get(package_type.lower())
        if not rule_path_component:
            self.logger.warning(f"No rule path mapped for package type: {package_type}")
            return []
        if rule_path_component not in compiled_rules_cache:
            compiled_rules_cache[rule_path_component] = self.load_rules(rule_path_component)
        return compiled_rules_cache[rule_path_component]

    def categorize_row(self, row):
        rules = self.get_compiled_rules(row['package_type'])
        for regex, top_cat, sub_cat in rules:
            if regex.search(row['name']):
                return pd.Series({"category": top_cat, "sub_category": sub_cat})
        return pd.Series({"category": "Other", "sub_category": ""})

    def bulk_update_dependencies(self, connection, updates):
        if not updates:
            return

        query = """
            UPDATE dependencies AS d
            SET 
                category = v.category,
                sub_category = v.sub_category
            FROM (VALUES %s) AS v(id, category, sub_category)
            WHERE d.id = v.id;
        """

        values = [(row["id"], row["category"], row["sub_category"]) for row in updates]

        with connection.connection.cursor() as cursor:
            execute_values(cursor, query, values)


if __name__ == '__main__':
    categorizer = CategoryAnalyzer()
    categorizer.run_analysis()
