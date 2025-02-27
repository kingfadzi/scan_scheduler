import os
from git import Repo, GitCommandError, InvalidGitRepositoryError
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, RepoMetrics
from modular.shared.execution_decorator import analyze_execution
from modular.shared.base_logger import BaseLogger  # Import BaseLogger for logging
import logging

class GitLogAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("GitLogAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Git Log Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):

        self.logger.info(f"Starting metrics calculation for repository: {repo.repo_name} (ID: {repo.repo_id})")

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        repo_obj = self.get_repo_object(repo_dir)
        if not repo_obj:
            error_message = f"Failed to access Git repository at {repo_dir}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if repo_obj.head.is_detached:
            self.logger.warning("Repository is in detached HEAD state")
            default_branch = None
        else:
            default_branch = repo_obj.active_branch.name
            self.logger.info(f"The default branch is: {default_branch}")

        if not default_branch:
            raise RuntimeError("Unable to determine the default branch of the repository.")

        self.logger.info(f"Calculating metrics from gitlog for repository directory: {repo_dir}")

        # Calculate metrics
        total_size = sum(blob.size for blob in repo_obj.tree(default_branch).traverse() if blob.type == 'blob')
        file_count = sum(1 for blob in repo_obj.tree(default_branch).traverse() if blob.type == 'blob')
        total_commits = sum(1 for _ in repo_obj.iter_commits(default_branch))
        contributors = set(commit.author.email for commit in repo_obj.iter_commits(default_branch))
        last_commit_date = max(commit.committed_datetime for commit in repo_obj.iter_commits(default_branch))
        first_commit_date = min(commit.committed_datetime for commit in repo_obj.iter_commits(default_branch))
        repo_age_days = (datetime.now(timezone.utc) - first_commit_date).days
        active_branch_count = len(repo_obj.branches)

        activity_status = "INACTIVE" if (datetime.now(timezone.utc) - last_commit_date).days > 365 else "ACTIVE"

        self.logger.info(f"Metrics for {repo.repo_name} (ID: {repo.repo_id}):")
        self.logger.info(f"  Total Size: {total_size} bytes")
        self.logger.info(f"  File Count: {file_count}")
        self.logger.info(f"  Total Commits: {total_commits}")
        self.logger.info(f"  Number of Contributors: {len(contributors)}")
        self.logger.info(f"  Last Commit Date: {last_commit_date}")
        self.logger.info(f"  Repository Age: {repo_age_days} days")
        self.logger.info(f"  Active Branch Count: {active_branch_count}")
        self.logger.info(f"  Activity Status: {activity_status}")

        session.execute(
            insert(RepoMetrics).values(
                repo_id=repo.repo_id,
                repo_size_bytes=total_size,
                file_count=file_count,
                total_commits=total_commits,
                number_of_contributors=len(contributors),
                last_commit_date=last_commit_date,
                repo_age_days=repo_age_days,
                active_branch_count=active_branch_count,
                activity_status=activity_status
            ).on_conflict_do_update(
                index_elements=['repo_id'],
                set_={
                    "repo_size_bytes": total_size,
                    "file_count": file_count,
                    "total_commits": total_commits,
                    "number_of_contributors": len(contributors),
                    "last_commit_date": last_commit_date,
                    "repo_age_days": repo_age_days,
                    "active_branch_count": active_branch_count,
                    "activity_status": activity_status,
                    "updated_at": datetime.now(timezone.utc)
                }
            )
        )
        session.commit()
        self.logger.info(f"Metrics saved for repository: {repo.repo_name} (ID: {repo.repo_id})")

        return (
            f"{repo.repo_name}: "
            f"{total_commits} commits, "
            f"{len(contributors)} contributors, "
            f"{file_count} files, "
            f"{total_size} bytes, "
            f"{repo_age_days} days old, "
            f"{activity_status} status, "
            f"{active_branch_count} branches, "
            f"last commit on {last_commit_date}."
        )

    def get_repo_object(self, repo_dir):

        try:
            repo_obj = Repo(repo_dir)
            return repo_obj
        except InvalidGitRepositoryError:
            self.logger.error(f"The directory {repo_dir} is not a valid Git repository.")
        except GitCommandError as e:
            self.logger.error(f"Git command error: {e}")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}")
        return None


if __name__ == "__main__":
    repo_slug = "WebGoat"
    repo_id = "WebGoat"
    activity_status = "ACTIVE"
    repo_dir = f"/tmp/{repo_slug}"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo(repo_id, repo_slug)
    session = Session()

    analyzer = GitLogAnalyzer()

    try:
        analyzer.logger.info(f"Running metrics calculation for hardcoded repo_id: {repo.repo_id}, repo_slug: {repo.repo_slug}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Standalone metrics calculation result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone metrics calculation: {e}")
    finally:
        session.close()
        analyzer.logger.info("Session closed.")
