import logging
from datetime import datetime 
import time 

from prefect.context import get_run_context
from sqlalchemy import text

from modular.shared.models import Session, Repository, AnalysisExecutionLog
from modular.shared.query_builder import build_query
import logging
import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def create_batches(payload, batch_size=1000, num_partitions=5):
    """Split repositories into parallel processing batches with detailed logging."""
    logger.info(
        f"Starting batch creation - Target batch size: {batch_size}, "
        f"Partitions: {num_partitions}"
    )

    all_repos = []
    for batch in fetch_repositories(payload, batch_size):
        all_repos.extend(batch)
        logger.debug(
            f"Accumulated {len(batch)} repos in current batch, "
            f"Total so far: {len(all_repos)}"
        )

    logger.info(f"Total repositories fetched: {len(all_repos)}")

    # Create partitioned batches
    partitions = [all_repos[i::num_partitions] for i in range(num_partitions)]
    partition_sizes = [len(p) for p in partitions]

    logger.info(
        f"Created {num_partitions} partitions with sizes: {partition_sizes} "
        f"(Standard deviation: {np.std(partition_sizes):.1f})"
    )

    return partitions


def fetch_repositories(payload, batch_size=1000):
    """Fetch repositories in paginated batches with detailed query logging."""
    logger.info(
        f"Initializing repository fetch - Payload: {payload.keys()}, "
        f"Page size: {batch_size}"
    )

    session = Session()
    offset = 0
    total_fetched = 0
    base_query = build_query(payload)

    logger.debug(f"Base SQL template:\n{base_query}")

    try:
        while True:
            final_query = f"{base_query} OFFSET {offset} LIMIT {batch_size}"
            logger.info(
                f"Executing paginated query - Offset: {offset:,}, "
                f"Limit: {batch_size}"
            )

            start_time = time.perf_counter()
            batch = session.query(Repository).from_statement(text(final_query)).all()
            query_time = time.perf_counter() - start_time

            batch_size_actual = len(batch)
            total_fetched += batch_size_actual

            logger.debug(
                f"Query completed in {query_time:.2f}s - "
                f"Returned {batch_size_actual} results\n"
                f"Sample results: {[r.repo_slug[:20] for r in batch[:3]]}..."
            )

            if not batch:
                logger.info("Empty result set - Ending pagination")
                break

            # Detach objects from session
            detach_start = time.perf_counter()
            for repo in batch:
                _ = repo.repo_slug  # Force attribute load
                session.expunge(repo)
            logger.debug(f"Detachment completed in {time.perf_counter() - detach_start:.2f}s")

            yield batch
            offset += batch_size

    finally:
        session.close()
        logger.info(
            f"Fetch completed - Total repositories retrieved: {total_fetched:,} "
            f"over {offset//batch_size} pages"
        )


def refresh_views():

    views_to_refresh = [
        "combined_repo_metrics",
        "combined_repo_violations",
        "combined_repo_metrics_api",
        "app_component_repo_mapping",
    ]

    session = Session()
    try:
        for view in views_to_refresh:
            logger.info(f"Refreshing materialized view: {view}")
            session.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))

        session.commit()
        logger.info("All materialized views refreshed successfully.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error refreshing materialized views: {e}")
    finally:
        session.close()

def determine_final_status(repo, run_id, session):

    logger.info(f"Determining status for {repo.repo_name} ({repo.repo_id}) run_id: {run_id}")
    statuses = (
        session.query(AnalysisExecutionLog.status)
        .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo.repo_id)
        .filter(AnalysisExecutionLog.status != "PROCESSING")
        .all()
    )

    if not statuses:
        repo.status = "ERROR"
        repo.comment = "No analysis records."
    elif any(s == "FAILURE" for (s,) in statuses):
        repo.status = "FAILURE"
    elif all(s == "SUCCESS" for (s,) in statuses):
        repo.status = "SUCCESS"
        repo.comment = "All steps completed."
    else:
        repo.status = "UNKNOWN"

    repo.updated_on = datetime.utcnow()
    session.add(repo)
    session.commit()


def generate_repo_flow_run_name():
    run_ctx = get_run_context()
    repo_slug = run_ctx.flow_run.parameters.get("repo_slug")
    return f"{repo_slug}"


def generate_main_flow_run_name():
    run_ctx = get_run_context()
    start_time = run_ctx.flow_run.expected_start_time
    formatted_time = start_time.strftime('%Y-%m-%d %H:%M:%S')

    # return f"{flow_name}_{formatted_time}"
    return f"{formatted_time}"
