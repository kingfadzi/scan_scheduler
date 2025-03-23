import os
import logging
import subprocess

from shared.language_required_decorator import language_required
from shared.models import Dependency,Session
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.utils import Utils


class GoDependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @language_required("go")
    @analyze_execution(session_factory=Session, stage="Go Dependency Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Processing repository at: {repo_dir}")
        utils = Utils()
        deps = []

        go_mod = os.path.join(repo_dir, "go.mod")
        go_sum = os.path.join(repo_dir, "go.sum")

        if not os.path.isfile(go_mod):
            self.logger.error("No go.mod file found. Skipping repository.")
            return "0 dependencies found."

        if not os.path.isfile(go_sum):
            self.logger.info("Generating go.sum using 'go mod tidy'.")
            try:
                subprocess.run(["go", "mod", "tidy"], cwd=repo_dir, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"'go mod tidy' failed: {e}")
                self.logger.debug(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
                return "0 dependencies found."

        if not os.path.isfile(go_sum):
            self.logger.error("go.sum file was not generated after running 'go mod tidy'.")
            return "0 dependencies found."

        try:
            deps = self.parse_go_modules(repo_dir, repo)
            utils.persist_dependencies(deps)
            return f"{len(deps)} dependencies found."
        except Exception as e:
            self.logger.error(f"Failed to parse Go modules: {str(e)}")
            return "0 dependencies found."

    def parse_go_modules(self, repo_dir, repo):
        try:
            result = subprocess.run(
                ["go", "list", "-m", "all"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True
            )
            dependencies = []
            lines = result.stdout.strip().split("\n")

            for line in lines[1:]:
                parts = line.split()
                module = parts[0]
                version = parts[1] if len(parts) > 1 else "unknown"
                dependencies.append(
                    Dependency(
                        repo_id=repo['repo_id'],
                        name=module,
                        version=version,
                        package_type="go"
                    )
                )
            return dependencies
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to list Go modules: {e}")
            self.logger.error(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
        return []

class Repo:
    def __init__(self, repo_id):
        self.repo_id = repo_id

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    helper = GoDependencyAnalyzer()
    repo_directory = "/Users/fadzi/tools/go_projetcs/ovaa"
    repo = Repo(repo_id="go_project")

    try:
        dependencies = helper.run_analysis(repo_directory, repo)
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")
