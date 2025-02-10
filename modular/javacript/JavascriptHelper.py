import os
import sys
import json
import logging
import subprocess

class JavaScriptHelper:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    def process_repo(self, repo_dir):
        pkg_lock = os.path.join(repo_dir, "package-lock.json")
        yarn_lock = os.path.join(repo_dir, "yarn.lock")
        if os.path.isfile(pkg_lock) or os.path.isfile(yarn_lock):
            self.logger.info("Lock file exists. Skipping repo.")
            return

        pkg_json_path = os.path.join(repo_dir, "package.json")
        if not os.path.isfile(pkg_json_path):
            self.logger.error("No package.json found in the repository.")
            return

        try:
            with open(pkg_json_path, "r") as f:
                pkg_data = json.load(f)
        except Exception as e:
            self.logger.error(f"Error reading package.json: {e}")
            return

        pm = "npm"
        if "packageManager" in pkg_data and "yarn" in pkg_data["packageManager"]:
            pm = "yarn"

        if pm == "yarn":
            cmd = ["yarn", "install"]
            lock_file = os.path.join(repo_dir, "yarn.lock")
        else:
            cmd = ["npm", "install"]
            lock_file = os.path.join(repo_dir, "package-lock.json")

        self.logger.info(f"Running {pm} install in repository.")
        try:
            subprocess.run(cmd, cwd=repo_dir, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"{pm} install failed: {e}")
            self.logger.debug(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
            return

        if not os.path.isfile(lock_file):
            self.logger.error("Lock file was not generated after install.")
            return

        self.logger.info(f"Lock file generated at: {lock_file}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python script.py /path/to/repo")
        sys.exit(1)
    repo_directory = sys.argv[1]
    helper = JavaScriptHelper()
    helper.process_repo(repo_directory)