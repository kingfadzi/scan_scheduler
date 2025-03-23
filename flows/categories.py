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

class CategoryAnalyzer(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    def bulk_update_dependencies(self, connection, updates):
        if not updates:
            self.logger.debug("No updates to apply to the database.")
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
        self.logger.debug(f"Executing bulk update for {len(values)} rows.")
        with connection.connection.cursor() as cursor:
            execute_values(cursor, query, values)
        self.logger.debug("Bulk update completed.")

def categorize_row(row, rules):
    for regex, top_cat, sub_cat in rules:
        if regex.search(row['name']):
            return pd.Series({"category": top_cat, "sub_category": sub_cat})
    return pd.Series({"category": "Other", "sub_category": ""})

@task
def refresh_materialized_view():
    logger = get_run_logger()
    logger.debug(f"Refreshing materialized view: {MATERIALIZED_VIEW}")
    with Session() as session:
        session.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW};"))
        session.commit()
    logger.debug(f"Materialized view {MATERIALIZED_VIEW} refreshed successfully.")

@task
def load_rules_for_type(package_type: str):
    logger = get_run_logger()
    component = RULES_MAPPING.get(package_type.lower())
    full_path = os.path.join(RULES_PATH, component)
    compiled_list = []

    logger.debug(f"Loading rules for package type '{package_type}' from '{full_path}'")

    if not component:
        logger.warning(f"No component found for package type '{package_type}'")
        return []

    if os.path.isdir(full_path):
        files = [os.path.join(full_path, f) for f in os.listdir(full_path) if f.endswith((".yml", ".yaml"))]
    else:
        files = [full_path]

    for file_path in files:
        try:
            logger.debug(f"Reading rule file: {file_path}")
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
            logger.error(f"Failed to load rules from {file_path}: {e}", exc_info=True)

    logger.debug(f"Loaded {len(compiled_list)} compiled rules for type '{package_type}'")
    return compiled_list

@task
def fetch_chunks_for_type(package_type: str) -> list:
    logger = get_run_logger()
    logger.debug(f"Fetching chunks for package type: {package_type}")
    with Session() as session:
        query = f"""
            SELECT d.id, d.repo_id, d.name, d.version, d.package_type, 
                   b.tool, b.tool_version, b.runtime_version
            FROM dependencies d 
            LEFT JOIN build_tools b ON d.repo_id = b.repo_id
            WHERE d.package_type = :ptype
        """
        chunks = []
        for idx, chunk in enumerate(pd.read_sql(text(query), params={"ptype": package_type}, con=session.connection(), chunksize=CHUNK_SIZE)):
            logger.debug(f"Fetched chunk {idx+1} with {len(chunk)} rows for '{package_type}'")
            if not chunk.empty:
                chunks.append(chunk)
            else:
                logger.warning(f"Chunk {idx+1} for '{package_type}' was empty")
        logger.debug(f"Total chunks fetched for '{package_type}': {len(chunks)}")
        return chunks

@task
def process_chunk_with_rules(chunk: pd.DataFrame, compiled_rules: list):
    context = get_run_context()
    logger = get_run_logger()
    run_id = context.task_run.flow_run_id

    chunk_size = len(chunk)
    logger.debug(f"[{run_id}] Starting chunk processing (rows={chunk_size})")
    logger.debug(f"[{run_id}] First row sample: {chunk.head(1).to_dict(orient='records')}")

    categorizer = CategoryAnalyzer(logger=logger, run_id=run_id)

    try:
        logger.debug(f"[{run_id}] Applying categorization rules...")
        cat_start = time.time()
        cat_values = chunk.apply(lambda row: categorize_row(row, compiled_rules), axis=1)
        chunk["category"] = cat_values["category"]
        chunk["sub_category"] = cat_values["sub_category"]
        logger.debug(f"[{run_id}] Categorization done in {time.time() - cat_start:.2f}s")

        updates = chunk[["id", "category", "sub_category"]].to_dict(orient="records")
        logger.debug(f"[{run_id}] Prepared {len(updates)} rows for bulk update")

        with Session() as session:
            logger.debug(f"[{run_id}] Executing bulk update...")
            categorizer.bulk_update_dependencies(session.connection(), updates)

        logger.info(f"[{run_id}] Processed chunk of {chunk_size} rows successfully.")
        return chunk_size

    except Exception as e:
        logger.error(f"[{run_id}] Exception during processing: {e}", exc_info=True)
        raise

@flow(name="Categorize Dependencies By Package Type")
def run_analysis_by_package_type():
    logger = get_run_logger()
    start = time.time()
    logger.info("Starting dependency categorization flow")
    refresh_materialized_view()

    package_types = list(RULES_MAPPING.keys())
    logger.debug(f"Processing the following package types: {package_types}")

    for package_type in package_types:
        logger.info(f"Starting rule load and chunk processing for '{package_type}'")

        rules = load_rules_for_type(package_type)
        chunks = fetch_chunks_for_type(package_type)

        if not chunks:
            logger.warning(f"No chunks to process for package type '{package_type}'")
            continue

        process_chunk_with_rules.map(chunks, unmapped(rules))
        logger.info(f"Completed processing for '{package_type}'")

    refresh_materialized_view()
    duration = time.time() - start
    logger.info(f"All processing completed in {duration:.2f} seconds.")

if __name__ == "__main__":
    print("Starting categorization flow from CLI...")
    run_analysis_by_package_type()