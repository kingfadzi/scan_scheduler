import subprocess
import venv

from shared.language_required_decorator import language_required
from shared.models import Dependency, Session
import os
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.utils import Utils


class PythonDependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("PythonHelper")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)


    @language_required("Python")
    @analyze_execution(session_factory=Session, stage="Python Dependency Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Processing repository at: {repo_dir}")
        env_path = self.create_virtual_env(repo_dir)
        req_file_path = os.path.join(repo_dir, "requirements.txt")

        if not (os.path.isfile(req_file_path) and os.path.getsize(req_file_path) > 0):
            self.logger.info("No valid requirements.txt found. Generating one using pipreqs.")
            try:
                self.generate_requirements_with_pipreqs(repo_dir)
            except Exception as e:
                self.logger.error(f"Failed to generate requirements.txt using pipreqs: {e}")
                Path(req_file_path).touch()

        self.install_requirements(repo_dir, env_path)
        final_req_file = self.freeze_requirements(repo_dir, env_path)

        if not os.path.isfile(final_req_file):
            return []

        lines = Path(final_req_file).read_text().splitlines()
        dependencies = [
            Dependency(repo_id=repo['repo_id'], name=name, version=version, package_type="pip")
            for line in lines if "==" in line
            for name, version in [line.split("==", 1)]
        ]

        self.logger.debug("Persisting dependencies to database...")
        utils = Utils()
        utils.persist_dependencies(dependencies)
        self.logger.debug("Dependencies persisted successfully.")

        msg = f"Found {len(dependencies)} dependencies."
        self.logger.info(msg)
        return msg


    def create_virtual_env(self, project_dir, env_name="venv"):
        env_path = os.path.join(project_dir, env_name)
        self.logger.info(f"Creating virtual environment in: {env_path}")
        if os.path.isdir(env_path):
            self.logger.warning(f"Virtual environment already exists at: {env_path}")
        else:
            try:
                venv.create(env_path, with_pip=True)
                self.logger.info("Virtual environment created successfully.")
            except Exception as e:
                self.logger.error(f"Error creating virtual environment: {e}")
                raise
        return env_path

    def install_requirements(self, project_dir, env_path, requirements_file="requirements.txt"):
        req_path = os.path.join(project_dir, requirements_file)
        if os.path.isfile(req_path):
            self.logger.info(f"Installing dependencies from {req_path}")
            pip_executable = os.path.join(env_path, "bin", "pip")
            command_list = [pip_executable, "install", "-r", req_path]
            self.logger.debug("Executing command: " + " ".join(command_list))
            try:
                result = subprocess.run(
                    command_list,
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                self.logger.info("Dependencies installed successfully.")
                self.logger.debug("pip install output: " + result.stdout)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install dependencies: {e}")
                self.logger.error(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
                raise
        else:
            self.logger.warning(f"{requirements_file} does not exist in {project_dir}. Skipping installation.")

    def freeze_requirements(self, project_dir, env_path, output_file="requirements.txt"):
        self.logger.info("Freezing the environment to generate an updated requirements file.")
        pip_executable = os.path.join(env_path, "bin", "pip")
        command_list = [pip_executable, "freeze"]
        try:
            result = subprocess.run(
                command_list,
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=True
            )
            output_path = os.path.join(project_dir, output_file)
            with open(output_path, "w") as f:
                f.write(result.stdout)
            self.logger.info(f"Requirements file generated at: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to run pip freeze: {e}")
            self.logger.error(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
            raise

    def generate_requirements_with_pipreqs(self, project_dir, output_file="requirements.txt"):
        self.logger.info("Generating requirements.txt using pipreqs.")
        output_path = os.path.join(project_dir, output_file)
        command_list = ["pipreqs", project_dir, "--force", "--savepath", output_path]
        try:
            result = subprocess.run(
                command_list,
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=True
            )
            self.logger.info("Requirements file generated by pipreqs.")
            self.logger.debug("pipreqs output: " + result.stdout)
            return output_path
        except subprocess.CalledProcessError as e:
            self.logger.error(f"pipreqs failed: {e}")
            self.logger.error(f"Stdout: {e.stdout}\nStderr: {e.stderr}")
            raise



import logging
from pathlib import Path

class Repo:
    def __init__(self, repo_id):
        self.repo_id = repo_id

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    helper = PythonDependencyAnalyzer()
    repo_directory = "/Users/fadzi/python_repos/Tiredful-API-py3-beta"
    repo = Repo(repo_id="dashboard")

    try:
        dependencies = helper.run_analysis(repo_directory, repo)
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version}")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")

