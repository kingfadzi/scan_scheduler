import os
import sys
import logging
import subprocess

class GoHelper:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    def process_repo(self, repo_dir):
        go_mod = os.path.join(repo_dir, "go.mod")
        go_sum = os.path.join(repo_dir, "go.sum")

        if not os.path.isfile(go_mod):
            self.logger.error("No go.mod file found. Skipping repository.")
            return

        if os.path.isfile(go_sum):
            self.logger.info("go.sum file already exists. Skipping dependency resolution.")
            return

        self.logger.info("Generating go.sum using 'go mod tidy'.")
        try:
            subprocess.run(["go", "mod", "tidy"], cwd=repo_dir, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"'go mod tidy' failed: {e}")
            self.logger.debug(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
            return

        if os.path.isfile(go_sum):
            self.logger.info(f"go.sum file generated successfully at: {go_sum}")
        else:
            self.logger.error("go.sum file was not generated after running 'go mod tidy'.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python script.py /path/to/repo")
        sys.exit(1)
    repo_directory = sys.argv[1]
    helper = GoHelper()
    helper.process_repo(repo_directory)