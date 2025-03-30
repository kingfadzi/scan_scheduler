import os
import logging
import subprocess
from pathlib import Path

from shared.models import Dependency, Session
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.utils import Utils

class PythonDependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.utils = Utils(logger=self.logger)

    @analyze_execution(
        session_factory=Session,
        stage="Python Dependency Analysis",
        require_language=["Python", "Jupyter Notebook"]
    )
    def run_analysis(self, repo_dir, repo):
        all_dependencies = []
        processed_dirs = []
        root_dir = Path(repo_dir)

        try:
            self.logger.info(f"Processing repository at: {repo_dir}")

            # Check root directory first
            root_requirements = root_dir / "requirements.txt"
            if root_requirements.exists() and self._is_python_project(root_dir):
                self.logger.info(f"Found requirements.txt in root directory: {root_dir}")
                processed_dirs.append(root_dir)
                dependencies = self._process_directory(root_dir, repo)
                all_dependencies.extend(dependencies)
            else:
                # Search subdirectories for requirements.txt
                for current_dir, _, _ in os.walk(repo_dir):
                    current_dir = Path(current_dir)
                    if current_dir == root_dir:
                        continue  # Skip root directory already checked

                    req_file = current_dir / "requirements.txt"
                    if req_file.exists() and self._is_python_project(current_dir):
                        self.logger.info(f"Found requirements.txt in subdirectory: {current_dir}")
                        processed_dirs.append(current_dir)
                        dependencies = self._process_directory(current_dir, repo)
                        all_dependencies.extend(dependencies)

            # If no processed directories, attempt to generate in root
            if not processed_dirs:
                if self._is_python_project(root_dir):
                    self.logger.info("No requirements.txt found. Generating in root directory.")
                    self._generate_requirements(root_dir)
                    req_file = root_dir / "requirements.txt"
                    if req_file.exists():
                        processed_dirs.append(root_dir)
                        dependencies = self._process_directory(root_dir, repo)
                        all_dependencies.extend(dependencies)
                    else:
                        self.logger.warning("Failed to generate requirements.txt in root directory")
                else:
                    self.logger.warning("No Python/Jupyter projects found in repository")
                    return "No Python/Jupyter projects found"

            self.logger.debug("Persisting dependencies to database...")
            self.utils.persist_dependencies(all_dependencies)

            msg = f"Found {len(all_dependencies)} dependencies across {len(processed_dirs)} directories"
            self.logger.info(msg)
            return msg

        except Exception as e:
            self.logger.exception(f"Error during analysis: {e}")
            raise

    def _is_python_project(self, directory):
        has_relevant_files = any(f.suffix in ('.py', '.ipynb') for f in directory.iterdir())
        has_req_file = (directory / "requirements.txt").exists()
        return has_relevant_files or has_req_file

    def _process_directory(self, directory, repo):
        try:
            self.logger.debug(f"Processing directory: {directory}")
            req_file = directory / "requirements.txt"

            if not req_file.exists() or req_file.stat().st_size == 0:
                if directory == Path(repo['repo_dir']):
                    self._generate_requirements(directory)
                else:
                    self.logger.info(f"Skipping empty/missing requirements.txt in {directory}")
                    return []

            return self._parse_dependencies(req_file, repo)

        except Exception as e:
            self.logger.error(f"Failed to process {directory}: {e}")
            return []

    def _generate_requirements(self, directory):
        try:
            self.logger.info(f"Generating requirements.txt in {directory}")
            subprocess.run(
                ["pipreqs", str(directory), "--force", "--savepath", "requirements.txt"],
                cwd=directory,
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            self.logger.error(f"pipreqs failed in {directory}: {e.stderr.decode()}")
            (directory / "requirements.txt").touch()

    def _parse_dependencies(self, req_file, repo):
        dependencies = []
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # Skip comments and empty lines

            # Handle common cases with version specifiers
            parts = line.split("==", 1) if "==" in line else [line, "unknown"]
            name = parts[0].split(">", 1)[0].split("<", 1)[0].split("~", 1)[0].strip()
            version = parts[1].strip() if len(parts) > 1 else "unknown"

            dependencies.append(Dependency(
                repo_id=repo['repo_id'],
                name=name,
                version=version,
                package_type="pip"
            ))
        return dependencies

class Repo:
    def __init__(self, repo_id, repo_dir):
        self.repo_id = repo_id
        self.repo_dir = repo_dir

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    analyzer = PythonDependencyAnalyzer()
    repo_directory = "/path/to/your/repository"
    repo = Repo(repo_id="example-repo", repo_dir=repo_directory)

    try:
        result = analyzer.run_analysis(repo_directory, repo)
        print(f"Analysis result: {result}")
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
