import logging
import os
from datetime import datetime

from sqlalchemy import text
from modular.models import Session, Repository, AnalysisExecutionLog
from modular.cloning import CloningAnalyzer
from modular.kantra_analysis import KantraAnalyzer
from modular.utils.query_builder import build_query
from modular.gitlog_analysis import GitLogAnalyzer
from modular.go_enry_analysis import GoEnryAnalyzer
from modular.lizard_analysis import LizardAnalyzer
from modular.cloc_analysis import ClocAnalyzer
from modular.syft_grype_analysis import SyftAndGrypeAnalyzer
from modular.trivy_analysis import TrivyAnalyzer
from modular.checkov_analysis import CheckovAnalyzer
from modular.semgrep_analysis import SemgrepAnalyzer
from modular.config import Config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def analyze_fundamentals(batch, run_id, **kwargs):
    session = Session()
    attached_batch = [session.merge(repo) for repo in batch]
    for repo in attached_batch:
        repo_dir = None
        try:
            logger.info(f"[Fundamentals] Processing repository: {repo.repo_name} (ID: {repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            logger.debug(f"[Fundamentals] Repository cloned to: {repo_dir}")

            LizardAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            ClocAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            GoEnryAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            GitLogAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

        except Exception as e:
            logger.error(f"[Fundamentals] Error processing repository {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            CloningAnalyzer().cleanup_repository_directory(repo_dir)
            logger.debug(f"[Fundamentals] Repository directory {repo_dir} cleaned up.")
        determine_final_status(repo, run_id, session)

    execute_sql_script("combined_repo_metrics.sql")

    session.close()

def analyze_vulnerabilities(batch, run_id, **kwargs):

    session = Session()
    attached_batch = [session.merge(repo) for repo in batch]
    for repo in attached_batch:
        repo_dir = None
        try:
            logger.info(f"[Vulnerabilities] Processing repository: {repo.repo_name} (ID: {repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            logger.debug(f"[Vulnerabilities] Repository cloned to: {repo_dir}")

            TrivyAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            SyftAndGrypeAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

        except Exception as e:
            logger.error(f"[Vulnerabilities] Error processing repository {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            CloningAnalyzer().cleanup_repository_directory(repo_dir)
            logger.debug(f"[Vulnerabilities] Repository directory {repo_dir} cleaned up.")
        determine_final_status(repo, run_id, session)
    session.close()


def analyze_standards_assessment(batch, run_id, **kwargs):

    session = Session()
    attached_batch = [session.merge(repo) for repo in batch]
    for repo in attached_batch:
        repo_dir = None
        try:
            logger.info(f"[Standards Assessment] Processing repository: {repo.repo_name} (ID: {repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            logger.debug(f"[Standards Assessment] Repository cloned to: {repo_dir}")

            CheckovAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)
            SemgrepAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

        except Exception as e:
            logger.error(f"[Standards Assessment] Error processing repository {repo.repo_name}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            CloningAnalyzer().cleanup_repository_directory(repo_dir)
            logger.debug(f"[Standards Assessment] Repository directory {repo_dir} cleaned up.")
        determine_final_status(repo, run_id, session)
    session.close()

def analyze_component_patterns(batch, run_id, **kwargs):

    session = Session()
    attached_batch = [session.merge(repo) for repo in batch]
    for repo in attached_batch:
        repo_dir = None
        try:
            logger.info(f"[Component Patterns] Processing repository: {repo.repo_id} (ID: {repo.repo_id})")
            repo_dir = CloningAnalyzer().clone_repository(repo=repo, run_id=run_id)
            logger.debug(f"[Component Patterns] Repository cloned to: {repo_dir}")

            KantraAnalyzer().run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id=run_id)

        except Exception as e:
            logger.error(f"[Component Patterns] Error processing repository {repo.repo_id}: {e}")
            repo.status = "ERROR"
            repo.comment = str(e)
            repo.updated_on = datetime.utcnow()
            session.add(repo)
            session.commit()
        finally:
            CloningAnalyzer().cleanup_repository_directory(repo_dir)
            logger.debug(f"[Component Patterns] Repository directory {repo_dir} cleaned up.")
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

def execute_sql_script(script_file_path):
    session = Session()
    try:

        sql_script_file_path = os.path.join(Config.SQL_SCRIPTS_DIR, script_file_path)

        with open(sql_script_file_path, "r") as file:
            sql_script = file.read()

        logger.info(f"Executing SQL script from {sql_script_file_path}.")
        session.execute(sql_script)
        session.commit()
        logger.info("SQL script executed successfully.")
    except Exception as e:
        logger.error(f"Error executing SQL script: {e}")
        session.rollback()

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
