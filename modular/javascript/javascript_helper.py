import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from modular.shared.models import Dependency
from modular.shared.base_logger import BaseLogger

class JavaScriptHelper(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("JavaScriptHelper")
        self.logger.setLevel(logging.DEBUG)

    def process_repo(self, repo_dir, repo):

        pkg_json_path = os.path.join(repo_dir, "package.json")
        lock_file = None

        if not os.path.isfile(pkg_json_path):
            self.logger.error("No package.json found in the repository.")
            return []

        pkg_lock = os.path.join(repo_dir, "package-lock.json")
        yarn_lock = os.path.join(repo_dir, "yarn.lock")

        if os.path.isfile(pkg_lock):
            lock_file = pkg_lock
        elif os.path.isfile(yarn_lock):
            lock_file = yarn_lock

        if lock_file:
            self.logger.info(f"Lock file {lock_file} exists. Parsing dependencies.")
            return self.parse_dependencies(lock_file, repo)

        self.logger.info("No lock file found. Installing dependencies to generate one.")
        pm = self.detect_package_manager(pkg_json_path)
        lock_file = pkg_lock if pm == "npm" else yarn_lock

        if not self.install_dependencies(repo_dir, pm, lock_file):
            return []

        return self.parse_dependencies(lock_file, repo) if os.path.isfile(lock_file) else []

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
            self.logger.debug(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
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
                                repo_id=repo.repo_id,
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
                                    repo_id=repo.repo_id,
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
    helper = JavaScriptHelper()

    try:
        dependencies = helper.process_repo(repo_directory, repo)
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")
