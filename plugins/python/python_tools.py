import json
import re
import logging
import os
import venv
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert

from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger

class PythonBuildToolAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.version_pattern = re.compile(r"==(\d+\.\d+\.\d+|\d+\.\d+)")
        self.utils = Utils(logger=logger)

    @analyze_execution(
        session_factory=Session,
        stage="Python Dependency Analysis",
        require_language=["Python", "Jupyter Notebook"]
    )
    def run_analysis(self, repo_dir, repo):
        all_dependencies = []
        requirements_locations = []
        root_dir = Path(repo_dir)
        central_venv = root_dir / "venv"

        try:
            self.logger.info(f"Analyzing repository: {repo_dir}")

            if self._is_python_project(root_dir):
                self.logger.info("Found root-level Python project")
                requirements_locations.append(root_dir)

            if not requirements_locations:
                self.logger.info("Scanning subdirectories for Python projects")
                for entry in root_dir.iterdir():
                    if entry.is_dir() and self._is_python_project(entry):
                        requirements_locations.append(entry)
                        self.logger.debug(f"Found subproject: {entry.name}")

            if not requirements_locations:
                self.logger.warning("No dependency files found, generating in root")
                requirements_locations.append(root_dir)

            if not central_venv.exists():
                self.logger.debug("Creating central virtual environment")
                venv.create(central_venv, with_pip=True)

            for location in requirements_locations:
                self.logger.info(f"Processing: {location.relative_to(root_dir)}")
                dependencies = self._process_location(location, repo, central_venv)
                all_dependencies.extend(dependencies)

            self.logger.debug(f"Persisting {len(all_dependencies)} dependencies")
            self.utils.persist_dependencies(all_dependencies)

            msg = (f"Found {len(all_dependencies)} dependencies "
                   f"across {len(requirements_locations)} locations")
            self.logger.info(msg)
            return msg

        except Exception as e:
            self.logger.exception(f"Analysis failed: {e}")
            raise

    def _process_directory(self, directory, repo, is_root=False):

        env_path = directory.parent / "venv" if not is_root else directory / "venv"

        if not env_path.exists():
            self.logger.debug(f"Creating central venv at: {env_path}")
            venv.create(env_path, with_pip=True)

        req_file = directory / "requirements.txt"
        if not req_file.exists() and is_root:
            self._generate_requirements(directory)

        self._install_requirements(directory, env_path)
        frozen_file = self._freeze_requirements(directory, env_path)

        return self._parse_dependencies(frozen_file, repo)


    def _validate_repo(self, repo):
        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        return 'Python' in repo_languages

    def _is_python_project(self, directory):

        project_files = {
            'requirements.txt',
            'pyproject.toml',
            'setup.py',
            'Pipfile',
            'poetry.lock'
        }

        if self._detect_build_tool(directory):
            return True

        if any((directory / f).exists() for f in project_files):
            return True

        return any(
            entry.is_file() and entry.suffix == '.py'
            for entry in directory.iterdir()
        )

    def _detect_build_tool(self, directory):
        tool_detectors = [
            ('poetry.lock', 'Poetry'),
            ('pyproject.toml', self._detect_poetry),
            ('Pipfile.lock', 'Pipenv'),
            ('Pipfile', 'Pipenv'),
            ('setup.py', 'Setuptools'),
            ('setup.cfg', 'Setuptools'),
            ('hatch.toml', 'Hatch')
        ]

        for file_name, detector in tool_detectors:
            if (directory / file_name).exists():
                if callable(detector):
                    if result := detector(directory):
                        return result
                else:
                    return detector
        return None

    def _detect_poetry(self, directory):
        try:
            with open(directory / 'pyproject.toml', 'r', encoding='utf-8') as f:
                if '[tool.poetry]' in f.read():
                    return 'Poetry'
        except Exception as e:
            self.logger.error(f"Error reading pyproject.toml: {e}")
        return None

    def _detect_python_version(self, directory, build_tool):
        version_detectors = {
            'Poetry': self._get_poetry_python_version,
            'Pipenv': self._get_pipenv_python_version,
            'Setuptools': self._get_setuptools_python_version
        }
        return version_detectors.get(build_tool, lambda _: "Unknown")(directory)

    def _detect_tool_version(self, directory, build_tool):
        version_detectors = {
            'Poetry': self._get_poetry_version,
            'Pipenv': self._get_pipenv_version,
            'Setuptools': self._get_setuptools_version
        }
        return version_detectors.get(build_tool, lambda _: "Unknown")(directory)

    def _persist_finding(self, repo, tool, py_ver, tool_ver):

        self.utils.persist_build_tool(
            build_tool=tool,
            repo_id_value=repo["repo_id"],
            tool_version=tool_ver,
            runtime_version=py_ver
        )

    def _get_poetry_python_version(self, directory):
        try:
            with open(directory / 'pyproject.toml', 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('python = '):
                        return line.split('=')[-1].strip().strip('"\'')
        except Exception as e:
            self.logger.error(f"Error parsing Python version: {e}")
        return "Unknown"

    def _get_poetry_version(self, directory):
        try:
            with open(directory / 'poetry.lock', 'r', encoding='utf-8') as f:
                for line in f:
                    if 'poetry-version' in line:
                        return line.split('=')[-1].strip().strip('"')
        except Exception:
            return "Unknown"

    def _get_pipenv_python_version(self, directory):
        try:
            with open(directory / 'Pipfile', 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('python_version'):
                        return line.split('=')[-1].strip().strip('"')
        except Exception:
            return "Unknown"

    def _get_pipenv_version(self, directory):
        try:
            with open(directory / 'Pipfile.lock', 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('_meta', {}).get('requires', {}).get('pip_version', 'Unknown')
        except Exception:
            return "Unknown"

    def _get_setuptools_python_version(self, directory):
        try:
            with open(directory / 'setup.py', 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'python_requires\s*=\s*["\']([^"\']+)["\']', content)
                return match.group(1) if match else "Unknown"
        except Exception:
            return "Unknown"

    def _get_setuptools_version(self, directory):
        try:
            with open(directory / 'setup.py', 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'setup_requires\s*=\s*\[([^\]]*)\]', content)
                if match:
                    version_match = re.search(r'setuptools(?:==|\s+)(\d+\.\d+\.?\d*)', match.group(1))
                    return version_match.group(1) if version_match else "Unknown"
            return "Unknown"
        except Exception:
            return "Unknown"

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    test_repo = MockRepo("python-build-test", "build-tool-analysis")
    test_repo_dir = "/path/to/test/repository"

    analyzer = PythonBuildToolAnalyzer()

    try:
        result = analyzer.run_analysis(
            repo_dir=test_repo_dir,
            repo=test_repo
        )
        print("Build Tool Analysis Results:")
        print(json.dumps(json.loads(result), indent=2))
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
