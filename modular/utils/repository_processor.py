import logging
from datetime import datetime
from sqlalchemy import text
from modular.models import Session, Repository, AnalysisExecutionLog
from modular.cloning import CloningAnalyzer
from modular.kantra_analysis import KantraAnalyzer
from modular.utils.query_builder import build_query

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def analyze_repositories(batch, run_id):
    session = Session()
    attached_batch = [session.merge(repo) for repo in batch]
    for repo in attached_batch:
        repo_dir = None
        try:
            logger.info(f"Processing: {repo.repo_name} ({repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            KantraAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
        except Exception as e:
            logger.error(f"Error for {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            if repo_dir:
                CloningAnalyzer().cleanup_repository_directory(repo_dir)
        determine_final_status(repo, run_id, session)
    session.close()

def determine_final_status(repo, run_id, session):
    logger.info(f"Determining status for {repo.repo_name} ({repo.repo_id}) run_id: {run_id}")
    statuses = session.query(AnalysisExecutionLog.status) \
        .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo.repo_id) \
        .filter(AnalysisExecutionLog.status != "PROCESSING") \
        .all()
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
        for repo in batch:
            session.expunge(repo)
        yield batch
        offset += batch_size
    session.close()

def create_batches(payload, batch_size=1000, num_tasks=5):
    all_repos = []
    for batch in fetch_repositories(payload, batch_size):
        all_repos.extend(batch)
    return [all_repos[i::num_tasks] for i in range(num_tasks)]

def main():
    sample_payload = {
        # 'repo_id': ['abc'],  # use LIKE '%abc%'
        'host_name': ['github.com'],
        'activity_status': ['ACTIVE'],
        # 'tc': ['some_tc_value'],
        'main_language': ['Python'],
        # 'classification_label': ['A'],
        # 'app_id': ['555'],
        # 'number_of_contributors': [5]
    }
    run_id = "test_run_001"
    batches = create_batches(sample_payload, batch_size=1000, num_tasks=5)

    session = Session()
    for i, batch in enumerate(batches):
        logger.info(f"Batch {i} contains {len(batch)} repositories:")
        for repo in batch:
            attached_repo = session.merge(repo)
            logger.info(
                f"Repository: repo_id={attached_repo.repo_id}, "
                f"repo_name={attached_repo.repo_name}, "
                f"status={attached_repo.status}, "
                f"comment={attached_repo.comment}, "
                f"updated_on={attached_repo.updated_on}"
            )
    session.close()

if __name__ == "__main__":
    main()
