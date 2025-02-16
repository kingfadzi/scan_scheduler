import os
import subprocess
import threading
import re
from modular.shared.models import Session, Repository, RepoMetrics
from modular.shared.execution_decorator import analyze_execution
from modular.shared.config import Config
from modular.shared.base_logger import BaseLogger
import logging

clone_semaphore = threading.Semaphore(10)

class CloningAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("CloningAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Clone Repository")
    def clone_repository(self, repo, timeout_seconds=300, run_id=None, sub_dir=None):
        self.logger.info(f"Starting cloning for repo: {repo.repo_id}")

        base_dir = os.path.abspath(Config.CLONED_REPOSITORIES_DIR)

        repo_dir = os.path.join(base_dir, repo.repo_slug)

        if sub_dir:
            repo_dir = os.path.join(base_dir, sub_dir, repo.repo_slug)

        os.makedirs(os.path.dirname(repo_dir), exist_ok=True)


        clone_url = self.ensure_ssh_url(repo)
        repo.clone_url_ssh = clone_url

        with clone_semaphore:
            try:
                ssh_command = (
                    "ssh -o StrictHostKeyChecking=no "
                    "-o UserKnownHostsFile=/dev/null "
                    "-o BatchMode=yes"
                )
                clone_command = (
                    f"rm -rf {repo_dir} && "
                    f"GIT_SSH_COMMAND='{ssh_command}' git clone {clone_url} {repo_dir}"
                )
                subprocess.run(
                    clone_command,
                    shell=True,
                    check=True,
                    timeout=timeout_seconds,
                    capture_output=True,
                    text=True,
                )
                self.logger.info(
                    f"Successfully cloned repository '{repo.repo_name}' to {repo_dir}."
                )
                return repo_dir
            except subprocess.TimeoutExpired:
                error_msg = (
                    f"Cloning repository {repo.repo_name} took too long (>{timeout_seconds}s)."
                )
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

        self.logger.info(f"Processing URL: {clone_url_ssh}")

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
        if repo_dir is not None and os.path.exists(repo_dir):
            try:
                subprocess.run(["rm", "-rf", repo_dir], check=True)
                self.logger.info(f"Cleaned up repository directory: {repo_dir}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to clean up repository directory: {repo_dir}. Error: {e}")
        else:
            self.logger.warning("Repository directory is None or does not exist. Skipping cleanup.")



if __name__ == "__main__":
    session = Session()

    repositories = (
        session.query(Repository)
        .join(RepoMetrics, Repository.repo_id == RepoMetrics.repo_id)
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
