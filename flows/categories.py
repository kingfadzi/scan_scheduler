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

    logger.info(f"[{package_type}] Loading rules from: {full_path}")

    if not component:
        logger.warning(f"[{package_type}] No component mapping found")
        return []

    if os.path.isdir(full_path):
        files = [os.path.join(full_path, f) for f in os.listdir(full_path) if f.endswith((".yml", ".yaml"))]
        logger.debug(f"[{package_type}] Found {len(files)} rule files in directory")
    else:
        files = [full_path]
        logger.debug(f"[{package_type}] Using single rule file")

    for file_path in files:
        try:
            logger.debug(f"[{package_type}] Processing file: {os.path.basename(file_path)}")
            with open(file_path, 'r') as f:
                rules = yaml.safe_load(f)
            
            for cat in rules.get('categories', []):
                category_name = cat['name']
                subcats = cat.get('subcategories', [])
                logger.debug(f"[{package_type}] Category: {category_name} ({len(subcats)} subcats)")

                if subcats:
                    for sub in subcats:
                        sub_name = sub.get('name', 'unnamed')
                        patterns = sub.get('patterns', [])
                        logger.debug(f"[{package_type}]  Subcategory: {sub_name} ({len(patterns)} patterns)")
                        for pattern in patterns:
                            compiled_list.append((re.compile(pattern, re.IGNORECASE), category_name, sub_name))
                else:
                    patterns = cat.get('patterns', [])
                    logger.debug(f"[{package_type}]  Top-level patterns: {len(patterns)}")
                    for pattern in patterns:
                        compiled_list.append((re.compile(pattern, re.IGNORECASE), category_name, ""))
            
            logger.info(f"[{package_type}] Loaded {len(rules.get('categories', []))} categories from {os.path.basename(file_path)}")

        except Exception as e:
            logger.error(f"[{package_type}] Failed to load rules: {str(e)}", exc_info=True)

    logger.info(f"[{package_type}] Total compiled rules: {len(compiled_list)}")
    return compiled_list

@task
def fetch_chunks_for_type(package_type: str) -> list:
    logger = get_run_logger()
    logger.info(f"[{package_type}] Fetching data chunks")
    with Session() as session:
        query = f"""
            SELECT d.id, d.repo_id, d.name, d.version, d.package_type, 
                   b.tool, b.tool_version, b.runtime_version
            FROM dependencies d 
            LEFT JOIN build_tools b ON d.repo_id = b.repo_id
            WHERE d.package_type = :ptype
        """
        chunks = []
        total_rows = 0
        for idx, chunk in enumerate(pd.read_sql(text(query), params={"ptype": package_type}, con=session.connection(), chunksize=CHUNK_SIZE)):
            chunk_size = len(chunk)
            total_rows += chunk_size
            logger.debug(f"[{package_type}] Chunk {idx+1}: {chunk_size} rows")
            if not chunk.empty:
                chunks.append(chunk)
                logger.debug(f"[{package_type}] Sample dependency: {chunk.iloc[0]['name']} ({chunk.iloc[0]['version']})")
            else:
                logger.warning(f"[{package_type}] Empty chunk {idx+1}")
        
        logger.info(f"[{package_type}] Total chunks: {len(chunks)} ({total_rows} rows)")
        return chunks

@task
def process_chunk_with_rules(chunk: pd.DataFrame, compiled_rules: list, package_type: str):
    context = get_run_context()
    logger = get_run_logger()
    run_id = context.task_run.flow_run_id

    chunk_size = len(chunk)
    logger.info(f"[{package_type}] Processing chunk ({chunk_size} rows)")
    logger.debug(f"[{package_type}] First dependency: {chunk.iloc[0]['name']}")

    categorizer = CategoryAnalyzer(logger=logger, run_id=run_id)

    try:
        logger.debug(f"[{package_type}] Applying {len(compiled_rules)} rules...")
        cat_start = time.time()
        
        def categorize_with_logging(row):
            result = categorize_row(row, compiled_rules)
            if result['category'] != 'Other':
                logger.debug(f"[{package_type}] Matched {row['name']} to {result['category']}/{result['sub_category']}")
            return result
            
        cat_values = chunk.apply(categorize_with_logging, axis=1)
        chunk["category"] = cat_values["category"]
        chunk["sub_category"] = cat_values["sub_category"]

        duration = time.time() - cat_start
        category_dist = chunk['category'].value_counts().to_dict()
        logger.debug(f"[{package_type}] Categorization stats ({duration:.2f}s):")
        for cat, count in category_dist.items():
            logger.debug(f"[{package_type}]  {cat}: {count} rows")

        updates = chunk[["id", "category", "sub_category"]].to_dict(orient="records")
        logger.debug(f"[{package_type}] Preparing {len(updates)} updates")

        with Session() as session:
            logger.info(f"[{package_type}] Starting bulk update")
            update_start = time.time()
            categorizer.bulk_update_dependencies(session.connection(), updates)
            logger.info(f"[{package_type}] Updated {len(updates)} rows in {time.time() - update_start:.2f}s")

        sample_output = chunk[['name', 'category', 'sub_category']].sample(min(3, len(chunk))).to_dict('records')
        logger.debug(f"[{package_type}] Sample results:")
        for item in sample_output:
            logger.debug(f"[{package_type}]  {item['name']} → {item['category']}/{item['sub_category']}")

        return chunk_size

    except Exception as e:
        logger.error(f"[{package_type}] Processing failed: {str(e)}", exc_info=True)
        raise

@flow(name="Categorize Dependencies By Package Type")
def run_analysis_by_package_type():
    logger = get_run_logger()
    start = time.time()
    logger.info("Starting dependency categorization flow")
    refresh_materialized_view()

    package_types = list(RULES_MAPPING.keys())
    logger.debug(f"Processing package types: {package_types}")

    for package_type in package_types:
        logger.info(f"\n===== Processing {package_type} =====")

        rules_future = load_rules_for_type.submit(package_type)
        chunks_future = fetch_chunks_for_type.submit(package_type)

        rules = rules_future.result()
        chunks = chunks_future.result()

        if not chunks:
            logger.warning(f"[{package_type}] No chunks to process")
            continue

        results = process_chunk_with_rules.map(chunks, unmapped(rules), unmapped(package_type))
        for result in results:
            result.result()

        logger.info(f"[{package_type}] Processing completed")

    refresh_materialized_view()
    duration = time.time() - start
    logger.info(f"All processing completed in {duration:.2f} seconds")

if __name__ == "__main__":
    print("Starting categorization flow...")
    run_analysis_by_package_type()