from prefect import flow, task, get_run_logger, unmapped
from prefect.context import get_run_context
import pandas as pd
import re
import yaml
import os
import time
import logging
from sqlalchemy import text
from psycopg2.extras import execute_values

from shared.models import Session
from config.config import Config
from shared.base_logger import BaseLogger

# Constants
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

# CategoryAnalyzer class
class CategoryAnalyzer(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

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

# Helper to apply rules to a row
def categorize_row(row, rules):
    for regex, top_cat, sub_cat in rules:
        if regex.search(row['name']):
            return pd.Series({"category": top_cat, "sub_category": sub_cat})
    return pd.Series({"category": "Other", "sub_category": ""})

# Task: Refresh materialized view
@task
def refresh_materialized_view():
    with Session() as session:
        session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
        session.commit()

# Task: Load rules once per package type
@task
def load_rules_for_type(package_type: str):
    component = RULES_MAPPING.get(package_type.lower())
    full_path = os.path.join(RULES_PATH, component)
    compiled_list = []

    if not component:
        return []

    if os.path.isdir(full_path):
        files = [os.path.join(full_path, f) for f in os.listdir(full_path) if f.endswith((".yml", ".yaml"))]
    else:
        files = [full_path]

    for file_path in files:
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
            print(f"Failed to load rules from {file_path}: {e}")

    return compiled_list

# Task: Get chunks for a given package type
@task
def fetch_chunks_for_type(package_type: str) -> list:
    with Session() as session:
        query = f"""
            SELECT d.id, d.repo_id, d.name, d.version, d.package_type, 
                   b.tool, b.tool_version, b.runtime_version
            FROM dependencies d 
            LEFT JOIN build_tools b ON d.repo_id = b.repo_id
            WHERE d.package_type = :ptype
        """
        chunks = []
        for chunk in pd.read_sql(text(query), params={"ptype": package_type}, con=session.connection(), chunksize=CHUNK_SIZE):
            if not chunk.empty:
                chunks.append(chunk)
        return chunks

# Task: Process one chunk with rules
@task
def process_chunk_with_rules(chunk: pd.DataFrame, compiled_rules: list):
    context = get_run_context()
    logger = get_run_logger()
    run_id = context.flow_run.id

    categorizer = CategoryAnalyzer(logger=logger, run_id=run_id)

    cat_values = chunk.apply(lambda row: categorize_row(row, compiled_rules), axis=1)
    chunk["category"] = cat_values["category"]
    chunk["sub_category"] = cat_values["sub_category"]
    updates = chunk[["id", "category", "sub_category"]].to_dict(orient="records")

    with Session() as session:
        categorizer.bulk_update_dependencies(session.connection(), updates)

    logger.info(f"Processed {len(chunk)} rows for {run_id}")
    return len(chunk)

# Main flow
@flow(name="Categorize Dependencies By Package Type")
def run_analysis_by_package_type():
    start = time.time()
    refresh_materialized_view()

    package_types = list(RULES_MAPPING.keys())

    for package_type in package_types:
        rules = load_rules_for_type(package_type)
        chunks = fetch_chunks_for_type(package_type)
        process_chunk_with_rules.map(chunks, unmapped(rules))

    refresh_materialized_view()
    duration = time.time() - start
    print(f"All processing completed in {duration:.2f} seconds.")

# Main entry point
if __name__ == "__main__":
    print("Starting categorization flow...")
    run_analysis_by_package_type()