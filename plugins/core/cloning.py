import asyncio
import os
import subprocess
import threading
import re
from shared.models import Session, Repository, RepoMetrics
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.base_logger import BaseLogger
import logging

from shared.utils import Utils

clone_semaphore = threading.Semaphore(10)

class CloningAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Clone Repository")
    def clone_repository(self, repo: dict, sub_dir=None):
        self.logger.info(f"Starting cloning for repo: {repo['repo_id']}")

        base_dir = os.path.abspath(Config.CLONED_REPOSITORIES_DIR)

        repo_dir = os.path.join(base_dir, repo["repo_slug"])

        if sub_dir:
            repo_dir = os.path.join(base_dir, sub_dir, repo["repo_slug"])

        os.makedirs(os.path.dirname(repo_dir), exist_ok=True)

        clone_url = self.ensure_ssh_url(repo)
        repo["clone_url_ssh"] = clone_url

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
                    timeout=Config.DEFAULT_PROCESS_TIMEOUT,
                    capture_output=True,
                    text=True,
                )
                self.logger.info(
                    f"Successfully cloned repository '{repo['repo_name']}' to {repo_dir}."
                )
                return repo_dir
            except subprocess.TimeoutExpired:
                error_msg = (
                    f"Cloning repository {repo['repo_name']} took too long (>{Config.DEFAULT_PROCESS_TIMEOUT}s)."
                )
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
            except subprocess.CalledProcessError as e:
                error_msg = (
                    f"Error cloning repository {repo['repo_name']}. "
                    f"Return code: {e.returncode}. Stderr: {e.stderr.strip()}"
                )
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)



    def ensure_ssh_url(self, repo: dict):
        clone_url_ssh = repo["clone_url_ssh"]
        host_name = repo["host_name"]

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




async def main():
    example_payload = {
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
            "main_language": ["Java"]
        }
    }

    utils = Utils()
    session = Session()
    analyzer = CloningAnalyzer(run_id="STANDALONE_RUN_ID_001")

    try:

        async for batch in utils.fetch_repositories_dict_async(payload=example_payload):
            for repo in batch:
                repo_dir = None
                try:
                    if not isinstance(repo, dict):
                        raise ValueError(f"Invalid repo format: {type(repo)}")

                    analyzer.logger.info(f"Processing repo: {repo.get('repo_slug', 'unknown')}")

                    repo_dir = analyzer.clone_repository(repo)

                except Exception as e:
                    analyzer.logger.error(f"Cloning failed for {repo.get('repo_slug', 'unknown')}: {str(e)}")
                finally:
                    if repo_dir:
                        analyzer.cleanup_repository_directory(repo_dir)
    finally:
        session.close()
        analyzer.logger.info("Standalone cloning process completed")

if __name__ == "__main__":
    asyncio.run(main())
