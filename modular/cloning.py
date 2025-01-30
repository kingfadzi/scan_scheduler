import os
import subprocess
import threading
import re
from modular.models import Session, Repository, RepoMetrics
from modular.execution_decorator import analyze_execution
from modular.config import Config
from modular.base_logger import BaseLogger
import logging

clone_semaphore = threading.Semaphore(10)

class CloningAnalyzer(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger()
        self.logger.setLevel(logging.WARN)

    @analyze_execution(session_factory=Session, stage="Clone Repository")
    def clone_repository(self, repo, timeout_seconds=300, run_id=None):

        self.logger.info(f"Starting cloning for repo: {repo.repo_id}")

        base_dir = Config.CLONED_REPOSITORIES_DIR
        repo_dir = f"{base_dir}/{repo.repo_slug}"
        os.makedirs(base_dir, exist_ok=True)

        # Ensure the URL is in SSH format
        clone_url = self.ensure_ssh_url(repo)
        repo.clone_url_ssh = clone_url

        with clone_semaphore:
            try:
                ssh_command = "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes"
                subprocess.run(
                    f"rm -rf {repo_dir} && GIT_SSH_COMMAND='{ssh_command}' git clone {clone_url} {repo_dir}",
                    shell=True,
                    check=True,
                    timeout=timeout_seconds,
                    capture_output=True,
                    text=True,
                )
                self.logger.info(f"Successfully cloned repository '{repo.repo_name}' to {repo_dir}.")
                return repo_dir
            except subprocess.TimeoutExpired:
                error_msg = f"Cloning repository {repo.repo_name} took too long (>{timeout_seconds}s)."
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
            except subprocess.CalledProcessError as e:
                error_msg = (
                    f"Error cloning repository {repo.repo_name}. "
                    f"Return code: {e.returncode}. Stderr: {e.stderr.strip()}"
                )
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)


    def ensure_ssh_url(self, repo):
        clone_url_ssh = repo.clone_url_ssh
        host_name = repo.host_name

        if not host_name:
            raise ValueError("repo.host_name is required")

        if clone_url_ssh.startswith("ssh://") or clone_url_ssh.startswith("git@"):
            return clone_url_ssh

        if not clone_url_ssh.startswith("https://"):
            raise ValueError(f"Unsupported URL format: {clone_url_ssh}")

        if host_name == "github.com":
            match = re.match(r"https://github\.com/([^/]+)/(.+?)(\.git)?$", clone_url_ssh)
            if not match:
                raise ValueError(f"URL not recognized as a valid GitHub URL: {clone_url_ssh}")
            owner_or_org, repo_slug, _ = match.groups()
            return f"git@github.com:{owner_or_org}/{repo_slug}.git"

        elif host_name == Config.BITBUCKET_HOSTNAME:
            match = re.match(r"https://([^/]+)/scm/([^/]+)/(.+?)(\.git)?$", clone_url_ssh)
            if not match:
                raise ValueError(f"URL not recognized as a valid Bitbucket URL: {clone_url_ssh}")
            domain, project_key, repo_slug, _ = match.groups()
            return f"ssh://git@{domain}:7999/{project_key}/{repo_slug}.git"

        elif host_name == Config.GITLAB_HOSTNAME:
            match = re.match(r"https://([^/]+)/([^/]+(?:/[^/]+)*)/(.+?)(\.git)?$", clone_url_ssh)
            if not match:
                raise ValueError(f"URL not recognized as a valid GitLab URL: {clone_url_ssh}")
            domain, group_path, repo_slug, _ = match.groups()
            return f"git@{domain}:{group_path}/{repo_slug}.git"

        else:
            raise ValueError(f"Unsupported host_name '{host_name}' for URL: {clone_url_ssh}")


    def cleanup_repository_directory(self, repo_dir):
        """
        Remove the cloned repository directory to free up space.
        """
        if os.path.exists(repo_dir):
            subprocess.run(f"rm -rf {repo_dir}", shell=True, check=True)
            self.logger.info(f"Cleaned up repository directory: {repo_dir}")


if __name__ == "__main__":
    session = Session()

    # Fetch a sample repository (status="NEW", just for demo)
    # repositories = session.query(Repository).filter_by(status="NEW").limit(1).all()

    repositories = (
        session.query(Repository)
        .join(RepoMetrics, Repository.repo_id == RepoMetrics.repo_id)  # Explicit join condition
        .filter(RepoMetrics.activity_status == 'ACTIVE')
        .limit(1)
        .all()
    )

    analyzer = CloningAnalyzer()

    for repo in repositories:

        repo_dir = None
        try:
            repo_dir = analyzer.clone_repository(repo, run_id="STANDALONE_RUN_001")

        except Exception as e:
            analyzer.logger.error(f"Cloning failed: {e}")
        finally:
            if repo_dir:
                analyzer.cleanup_repository_directory(repo_dir)

    session.close()
