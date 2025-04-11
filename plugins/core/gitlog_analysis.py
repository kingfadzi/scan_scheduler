import os
from collections import Counter

from git import Repo, GitCommandError, InvalidGitRepositoryError
from datetime import datetime, timezone, timedelta
from sqlalchemy.dialects.postgresql import insert
from shared.models import Session, RepoMetrics
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
import logging

class GitLogAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Git Log Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting metrics calculation for repository: {repo['repo_name']} (ID: {repo['repo_id']})")

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

        total_size = sum(blob.size for blob in repo_obj.tree(default_branch).traverse() if blob.type == 'blob')
        file_count = sum(1 for blob in repo_obj.tree(default_branch).traverse() if blob.type == 'blob')
        total_commits = sum(1 for _ in repo_obj.iter_commits(default_branch))
        contributors = set(commit.author.email for commit in repo_obj.iter_commits(default_branch))
        last_commit_date = max(commit.committed_datetime for commit in repo_obj.iter_commits(default_branch))
        first_commit_date = min(commit.committed_datetime for commit in repo_obj.iter_commits(default_branch))
        repo_age_days = (datetime.now(timezone.utc) - first_commit_date).days
        active_branch_count = len(repo_obj.branches)
        activity_status = "INACTIVE" if (datetime.now(timezone.utc) - last_commit_date).days > 365 else "ACTIVE"
        commit_authors = [commit.author.email for commit in repo_obj.iter_commits(default_branch)]
        author_commit_counts = Counter(commit_authors)

        if author_commit_counts:
            top_contributor_commits = author_commit_counts.most_common(1)[0][1]
        else:
            top_contributor_commits = 0

        commits_by_top_3_contributors = sum(count for _, count in author_commit_counts.most_common(3))
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=365)
        recent_commit_dates = [
            commit.committed_datetime
            for commit in repo_obj.iter_commits(default_branch)
            if commit.committed_datetime >= cutoff_date
        ]

        metrics = {
            "repo_id": repo["repo_id"],
            "repo_size_bytes": total_size,
            "file_count": file_count,
            "total_commits": total_commits,
            "number_of_contributors": len(contributors),
            "last_commit_date": last_commit_date,
            "repo_age_days": repo_age_days,
            "active_branch_count": active_branch_count,
            "activity_status": activity_status,
            "top_contributor_commits": top_contributor_commits,
            "commits_by_top_3_contributors": commits_by_top_3_contributors,
            "recent_commit_dates": recent_commit_dates,
        }

        self.persist_repo_metrics(metrics)
        self.logger.info(f"Metrics saved for repository: {repo['repo_name']} (ID: {repo['repo_id']})")

        return (
            f"{repo['repo_name']}: "
            f"{total_commits} commits, "
            f"{len(contributors)} contributors, "
            f"{file_count} files, "
            f"{total_size} bytes, "
            f"{repo_age_days} days old, "
            f"{activity_status} status, "
            f"{active_branch_count} branches, "
            f"last commit on {last_commit_date}."
        )

    def persist_repo_metrics(self, metrics):
        session = Session()
        try:
            session.query(RepoMetrics).filter(
                RepoMetrics.repo_id == metrics["repo_id"]
            ).delete()

            repo_metrics = RepoMetrics(
                repo_id=metrics["repo_id"],
                repo_size_bytes=metrics["repo_size_bytes"],
                file_count=metrics["file_count"],
                total_commits=metrics["total_commits"],
                number_of_contributors=metrics["number_of_contributors"],
                last_commit_date=metrics["last_commit_date"],
                repo_age_days=metrics["repo_age_days"],
                active_branch_count=metrics["active_branch_count"],
                activity_status=metrics["activity_status"],
                top_contributor_commits=metrics["top_contributor_commits"],
                commits_by_top_3_contributors=metrics["commits_by_top_3_contributors"],
                recent_commit_dates=metrics["recent_commit_dates"],
                updated_at=datetime.now(timezone.utc)
            )
            session.add(repo_metrics)
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.exception(f"Error persisting repo metrics for repo_id {metrics['repo_id']}: {e}")
            raise
        finally:
            session.close()

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


import sys
import os

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py /path/to/repo_dir")
        sys.exit(1)

    repo_dir = sys.argv[1]
    repo_name = os.path.basename(os.path.normpath(repo_dir))
    repo_slug = repo_name
    repo_id = f"standalone_test/{repo_slug}"
    activity_status = "ACTIVE"

    repo = {
        "repo_id": repo_id,
        "repo_slug": repo_slug,
        "repo_name": repo_name
    }

    session = Session()
    analyzer = GitLogAnalyzer(run_id="STANDALONE_RUN_ID_001")

    try:
        analyzer.logger.info(f"Running metrics calculation for repo_dir: {repo_dir}, repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone metrics calculation result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone metrics calculation: {e}")
    finally:
        session.close()
        analyzer.logger.info("Session closed.")

