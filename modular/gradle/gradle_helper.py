import os
import uuid
from modular.base_logger import BaseLogger
from modular.gradle.environment_manager import GradleEnvironmentManager
from modular.gradle.snippet_builder import GradleSnippetBuilder
from modular.gradle.gradle_runner import GradleRunner
import logging

class GradleHelper(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleHelper")
        self.logger.setLevel(logging.DEBUG)

        self.environment_manager = GradleEnvironmentManager()
        self.snippet_builder = GradleSnippetBuilder()
        self.runner = GradleRunner()

    def generate_resolved_dependencies(self, repo_dir, output_file="all-deps-nodupes.txt"):
        if not os.path.isdir(repo_dir):
            self.logger.error(f"Invalid directory: {repo_dir}")
            return None

            try:
                gradle_env = self.environment_manager.get_gradle_environment(repo_dir)
                if not gradle_env or not gradle_env.get("gradle_executable"):
                    self.logger.warning(f"Skipping dependency generation for {repo_dir} due to missing Gradle executable.")
                    return None
            except Exception as ex:
                self.logger.error(f"Error fetching Gradle environment for {repo_dir}: {ex}")
                return None

            gradle_executable = gradle_env["gradle_executable"]
            java_home = gradle_env.get("JAVA_HOME", "Not Set")
        try:
            gradle_version = self.environment_manager._detect_gradle_version(repo_dir)
        except Exception as ex:
            self.logger.error(f"Error detecting Gradle version for {repo_dir}: {ex}")
            return None

        if not gradle_version:
            self.logger.error(f"Failed to detect Gradle version for {repo_dir}.")
            return None

        self.logger.debug(f"Selected Gradle executable: {gradle_executable}")
        self.logger.debug(f"Selected JAVA_HOME: {java_home}")
        self.logger.debug(f"Detected Gradle version: {gradle_version}")

        # debugging Gradle environment
        self.logger.debug(f"Gradle environment: {gradle_env}")

        try:
            build_file = self._ensure_root_build_file(repo_dir)
            if not build_file:
                self.logger.error("Failed to find or create a root build file.")
                return None
        except Exception as ex:
            self.logger.error(f"Error ensuring root build file: {ex}")
            return None

        task_name = f"allDependenciesNoDupes_{uuid.uuid4().hex[:8]}"
        snippet = self.snippet_builder.build_snippet(gradle_version, task_name)
        self._inject_snippet(build_file, snippet)

        cmd = [
            gradle_executable,
            # "--no-daemon",
            # "--no-parallel",
            task_name
        ]

        try:
            result = self.runner.run(
                cmd=cmd,
                cwd=repo_dir,
                gradle_version=gradle_version,
                check=True
            )
            if not result or result.returncode != 0:
                self.logger.warning("Custom task failed; attempting fallback 'dependencies' command.")
                return self._fallback_dependencies(repo_dir, gradle_executable, output_file, gradle_version)
        except Exception as ex:
            self.logger.error(f"Error running Gradle task: {ex}")
            return None

        return self._find_output_file(repo_dir, output_file)

def _fallback_dependencies(self, repo_dir, gradle_executable, output_file, gradle_version):
    cmd = [
        gradle_executable,
        # "--no-daemon",
        # "--no-parallel",
        "dependencies"
    ]

    try:
        result = self.runner.run(
            cmd=cmd,
            cwd=repo_dir,
            gradle_version=gradle_version,
            check=False
        )
        if not result or result.returncode != 0:
            self.logger.error("Fallback 'dependencies' command also failed.")
            return None
    except Exception as ex:
        self.logger.error(f"Error running fallback 'dependencies' command: {ex}")
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
                f.write("// Additional config may be placed here if desired.\n")
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

if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) > 1:
        repo = sys.argv[1]
    else:
        repo = "/Users/fadzi/tools/Open-Vulnerability-Project"

    helper = GradleHelper()
    deps_file = helper.generate_resolved_dependencies(repo)
    if deps_file:
        print(f"Dependencies file: {deps_file}")
    else:
        print("Failed to generate dependencies.")
