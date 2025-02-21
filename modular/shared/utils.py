import logging
from datetime import datetime

from prefect.context import get_run_context
from sqlalchemy import text

from modular.shared.models import Session, Repository, AnalysisExecutionLog
from modular.shared.query_builder import build_query

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def create_batches(payload, batch_size=1000, num_partitions=5):

    all_repos = []
    for batch in fetch_repositories(payload, batch_size):
        all_repos.extend(batch)
    # Distribute repositories into num_partitions batches (using round-robin distribution)
    return [all_repos[i::num_partitions] for i in range(num_partitions)]


def fetch_repositories(payload, batch_size=1000):

    session = Session()
    offset = 0
    base_query = build_query(payload)
    logger.info(f"Built query: {base_query}")

    while True:
        final_query = f"{base_query} OFFSET {offset} LIMIT {batch_size}"
        logger.info(f"Executing query: {final_query}")
        batch = session.query(Repository).from_statement(text(final_query)).all()
        if not batch:
            break
        # Detach each repository from the session.
        for repo in batch:
            _ = repo.repo_slug # Access the attribute so it gets loaded.
            session.expunge(repo)
        yield batch
        offset += batch_size

    session.close()

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
