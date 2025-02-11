import os
import sys
import logging
import subprocess
from pathlib import Path
from modular.shared.models import Dependency

class GoHelper:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)

    def process_repo(self, repo_dir, repo):

        self.logger.info(f"Processing repository at: {repo_dir}")

        go_mod = os.path.join(repo_dir, "go.mod")
        go_sum = os.path.join(repo_dir, "go.sum")

        if not os.path.isfile(go_mod):
            self.logger.error("No go.mod file found. Skipping repository.")
            return []

        if not os.path.isfile(go_sum):
            self.logger.info("Generating go.sum using 'go mod tidy'.")
            try:
                subprocess.run(["go", "mod", "tidy"], cwd=repo_dir, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"'go mod tidy' failed: {e}")
                self.logger.debug(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
                return []

        if not os.path.isfile(go_sum):
            self.logger.error("go.sum file was not generated after running 'go mod tidy'.")
            return []

        return self.parse_go_modules(repo_dir, repo)

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
            # Skip the first line as it represents the main module.
            for line in lines[1:]:
                parts = line.split()
                module = parts[0]
                version = parts[1] if len(parts) > 1 else "unknown"
                dependencies.append(
                    Dependency(
                        repo_id=repo.repo_id,
                        name=module,
                        version=version,
                        package_type="go"
                    )
                )
            return dependencies
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to list Go modules: {e}")
            self.logger.debug(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
        return []


# Define Repo class similar to PythonHelper
class Repo:
    def __init__(self, repo_id):
        self.repo_id = repo_id

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    helper = GoHelper()
    repo_directory = "/Users/fadzi/tools/go_project"
    repo = Repo(repo_id="go_project")

    try:
        dependencies = helper.process_repo(repo_directory, repo)
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")
