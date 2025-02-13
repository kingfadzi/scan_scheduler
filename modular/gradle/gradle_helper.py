import os
import uuid
import logging
from pathlib import Path
from modular.shared.base_logger import BaseLogger
from modular.gradle.environment_manager import GradleEnvironmentManager
from modular.gradle.snippet_builder import GradleSnippetBuilder
from modular.gradle.gradle_runner import GradleRunner
from modular.shared.models import Dependency  # Assuming Dependency model is similar to PythonHelper

class GradleHelper(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleHelper")
        self.logger.setLevel(logging.DEBUG)

        self.environment_manager = GradleEnvironmentManager()
        self.snippet_builder = GradleSnippetBuilder()
        self.runner = GradleRunner()

    def process_repo(self, repo_dir, repo):

        gradle_files = ["build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"]
        if not any(os.path.isfile(os.path.join(repo_dir, f)) for f in gradle_files):
            self.logger.info(f"No Gradle build files found in {repo_dir}. Skipping.")
            return []

        output_file = "all-deps-nodupes.txt"
        self.logger.info(f"Generating resolved dependencies for {repo_dir}.")
        dependencies_file = self.generate_resolved_dependencies(repo_dir, output_file)

        if not dependencies_file or not os.path.isfile(dependencies_file):
            self.logger.error(f"Failed to generate dependencies for {repo_dir}")
            return []

        return self.parse_dependencies(dependencies_file, repo)

    def generate_resolved_dependencies(self, repo_dir, output_file="all-deps-nodupes.txt"):
        if not os.path.isdir(repo_dir):
            self.logger.error(f"Invalid directory: {repo_dir}")
            return None

        gradle_env = self.environment_manager.get_gradle_environment(repo_dir)
        if not gradle_env or not gradle_env["gradle_executable"]:
            self.logger.warning(f"Skipping dependency generation for {repo_dir} due to missing Gradle executable.")
            return None

        gradle_executable = gradle_env["gradle_executable"]
        gradle_version = self.environment_manager._detect_gradle_version(repo_dir)

        if not gradle_version:
            self.logger.error(f"Failed to detect Gradle version for {repo_dir}.")
            return None

        self.logger.debug(f"Gradle executable: {gradle_executable}")
        self.logger.debug(f"Detected Gradle version: {gradle_version}")

        build_file = self._ensure_root_build_file(repo_dir)
        if not build_file:
            self.logger.error("Failed to find or create a root build file.")
            return None

        task_name = f"allDependenciesNoDupes_{uuid.uuid4().hex[:8]}"
        snippet = self.snippet_builder.build_snippet(gradle_version, task_name)
        self._inject_snippet(build_file, snippet)

        cmd = [gradle_executable, task_name]
        result = self.runner.run(cmd=cmd, cwd=repo_dir, gradle_version=gradle_version, check=True)

        if not result or result.returncode != 0:
            self.logger.warning("Custom task failed; attempting fallback 'dependencies' command.")
            return self._fallback_dependencies(repo_dir, gradle_executable, output_file, gradle_version)

        return self._find_output_file(repo_dir, output_file)

    def parse_dependencies(self, dependencies_file, repo):
        """Parses the Gradle dependencies file and returns a list of Dependency objects with repo_id."""
        dependencies = []
        if not os.path.isfile(dependencies_file):
            return dependencies

        with open(dependencies_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "---" in line:
                continue

            parts = line.split(":")
            if len(parts) >= 3:
                group, name, version = parts[0], parts[1], parts[2]
                dependencies.append(
                    Dependency(
                        repo_id=repo.repo_id,
                        name=f"{group}:{name}",
                        version=version,
                        package_type="gradle"
                    )
                )
        return dependencies

    def _fallback_dependencies(self, repo_dir, gradle_executable, output_file, gradle_version):
        cmd = [gradle_executable, "dependencies"]
        result = self.runner.run(cmd=cmd, cwd=repo_dir, gradle_version=gradle_version, check=False)

        if not result or result.returncode != 0:
            self.logger.error("Fallback 'dependencies' command also failed.")
            return None

        path = os.path.join(repo_dir, output_file)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            self.logger.info(f"Fallback output written to {path}")
            return path
        except Exception as ex:
            self.logger.error(f"Error writing fallback output: {ex}")
            return None

    def _ensure_root_build_file(self, repo_dir):
        for fname in ["build.gradle", "build.gradle.kts"]:
            path = os.path.join(repo_dir, fname)
            if os.path.isfile(path):
                self.logger.debug(f"Found existing root build file: {path}")
                return path

        minimal_build = os.path.join(repo_dir, "build.gradle")
        try:
            with open(minimal_build, "w", encoding="utf-8") as f:
                f.write("// Minimal root build file for enumerating dependencies.\n")
            self.logger.info(f"Created minimal build.gradle at {minimal_build}")
            return minimal_build
        except Exception as ex:
            self.logger.error(f"Failed to create minimal build file: {ex}")
            return None

    def _inject_snippet(self, build_file, snippet):
        self.logger.debug(f"Injecting snippet into {build_file}")
        try:
            with open(build_file, "a", encoding="utf-8") as f:
                f.write(f"\n{snippet}\n")
        except Exception as e:
            self.logger.error(f"Failed to inject snippet into {build_file}: {e}")

    def _find_output_file(self, repo_dir, output_file):
        candidates = [
            os.path.join(repo_dir, "build", "reports", output_file),
            os.path.join(repo_dir, output_file)
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

# Define Repo class similar to PythonHelper
class Repo:
    def __init__(self, repo_id):
        self.repo_id = repo_id

if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) > 1:
        repo_directory = sys.argv[1]
    else:
        repo_directory = "/Users/fadzi/tools/gradle_projects/ovaa"

    repo = Repo(repo_id="Open-Vulnerability-Project")  # Replace with actual repo_id logic
    helper = GradleHelper()

    try:
        dependencies = helper.process_repo(repo_directory, repo)
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")
