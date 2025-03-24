import os
import sys
import json
import logging
import subprocess

from shared.language_required_decorator import language_required
from shared.models import Dependency, Session
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.utils import Utils


class JavaScriptDependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)


    @analyze_execution(
        session_factory=Session,
        stage="Javascript Dependency Analysis",
        require_language=["JavaScript", "TypeScript"]
    )
    def run_analysis(self, repo_dir, repo):
        try:
            pkg_json_path = os.path.join(repo_dir, "package.json")
            lock_file = None
            utils = Utils()  # Create Utils instance once

            if not os.path.isfile(pkg_json_path):
                self.logger.warn("No package.json found in the repository.")
                return "0 dependencies found."

            pkg_lock = os.path.join(repo_dir, "package-lock.json")
            yarn_lock = os.path.join(repo_dir, "yarn.lock")

            if os.path.isfile(pkg_lock):
                lock_file = pkg_lock
            elif os.path.isfile(yarn_lock):
                lock_file = yarn_lock

            if lock_file:
                self.logger.info(f"Lock file {lock_file} exists. Parsing dependencies.")
                dependencies = self.parse_dependencies(lock_file, repo)
                utils.persist_dependencies(dependencies)  # Persist here
                return f"{len(dependencies)} dependencies found."

            self.logger.info("No lock file found. Installing dependencies to generate one.")
            pm = self.detect_package_manager(pkg_json_path)
            lock_file = pkg_lock if pm == "npm" else yarn_lock

            if not self.install_dependencies(repo_dir, pm, lock_file):
                return "0 dependencies found."

            if os.path.isfile(lock_file):
                dependencies = self.parse_dependencies(lock_file, repo)
                utils.persist_dependencies(dependencies)  # Persist here too
                return f"{len(dependencies)} dependencies found."

            return "0 dependencies found."
        except Exception as e:
            self.logger.error(f"Exception occurred during analysis: {e}", exc_info=True)
            raise

    def detect_package_manager(self, pkg_json_path):

        try:
            with open(pkg_json_path, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
            return "yarn" if "packageManager" in pkg_data and "yarn" in pkg_data["packageManager"] else "npm"
        except Exception as e:
            self.logger.error(f"Error reading package.json: {e}")
            return "npm"

    def install_dependencies(self, repo_dir, pm, lock_file):

        cmd = ["yarn", "install"] if pm == "yarn" else ["npm", "install"]
        self.logger.info(f"Running {pm} install in repository.")
        try:
            subprocess.run(cmd, cwd=repo_dir, check=True, capture_output=True, text=True)
            if os.path.isfile(lock_file):
                self.logger.info(f"Lock file generated at: {lock_file}")
                return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"{pm} install failed: {e}")
            self.logger.error(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
        return False


    def parse_dependencies(self, lock_file, repo):

        dependencies = []
        if not os.path.isfile(lock_file):
            return dependencies

        if lock_file.endswith("package-lock.json"):
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)

                if "dependencies" in lock_data:
                    for name, details in lock_data["dependencies"].items():
                        version = details.get("version", "unknown")
                        dependencies.append(
                            Dependency(
                                repo_id=repo['repo_id'],
                                name=name,
                                version=version,
                                package_type="npm"
                            )
                        )

            except Exception as e:
                self.logger.error(f"Error parsing package-lock.json: {e}")

        elif lock_file.endswith("yarn.lock"):
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                name = None
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if ":" in line:
                            name = line.split(":")[0].strip().strip('"')
                        elif name and line.startswith("version"):
                            version = line.split(" ")[-1].strip().strip('"')
                            dependencies.append(
                                Dependency(
                                    repo_id=repo['repo_id'],
                                    name=name,
                                    version=version,
                                    package_type="yarn"
                                )
                            )
                            name = None
            except Exception as e:
                self.logger.error(f"Error parsing yarn.lock: {e}")

        return dependencies


class Repo:
    def __init__(self, repo_id):
        self.repo_id = repo_id

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python script.py /path/to/repo")
        sys.exit(1)

    repo_directory = sys.argv[1]
    repo = Repo(repo_id="node_project")  # Replace with actual repo_id logic
    helper = JavaScriptDependencyAnalyzer()

    try:
        dependencies = helper.run_analysis(repo_directory, repo)
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")
