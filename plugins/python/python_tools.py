import re
import sys
import logging
import subprocess
import venv
import json
from pathlib import Path
from typing import Optional, Dict, ClassVar

from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger
from sqlalchemy.dialects.postgresql import insert

class PythonBuildToolAnalyzer(BaseLogger):
    VERSION_PATTERN = re.compile(
        r"^(?P<name>[\w.-]+)"
        r"(?P<specifiers>(?:==|>=|<=|~=|!=|<|>|===|@)\S+)?"
    )
    USE_VENV_FALLBACK: ClassVar[bool] = False  # Not used in build-tool-only mode

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.utils = Utils(logger=logger)
        self.build_tool_detectors = [
            ('poetry.lock', 'Poetry'),
            ('pyproject.toml', self._detect_poetry),
            ('Pipfile.lock', 'Pipenv'),
            ('Pipfile', 'Pipenv'),
            ('setup.py', 'Setuptools'),
            ('setup.cfg', 'Setuptools'),
            ('hatch.toml', 'Hatch')
        ]
        self.logger.debug("Initialized PythonBuildToolAnalyzer (build tools only)")

    @analyze_execution(
        session_factory=Session,
        stage="Python Build Tool Analysis",
        require_language=["Python", "Jupyter Notebook"]
    )
    def run_analysis(self, repo_dir, repo):
        self.logger.debug(f"Starting build tool analysis on repo {repo.get('repo_id', 'unknown')} in {repo_dir}")
        root_dir = Path(repo_dir)
        self.logger.debug(f"Resolved repository directory: {root_dir.resolve()}")
        build_tools = set()

        # Loop through each detector and check if the corresponding file exists.
        for file_name, detector in self.build_tool_detectors:
            target = root_dir / file_name
            self.logger.debug(f"Checking for '{file_name}' in {root_dir}")
            if target.exists():
                tool_name = detector(target) if callable(detector) else detector
                if tool_name:
                    detected_info = {
                        'repo_id': repo['repo_id'],
                        'tool': tool_name,
                        'tool_version': self._detect_tool_version(root_dir, tool_name),
                        'runtime_version': self._detect_python_version(root_dir, tool_name)
                    }
                    self.logger.debug(f"Detected build tool info: {detected_info}")
                    build_tools.add(detected_info)

        self.logger.debug(f"Persisting {len(build_tools)} build tools")
        self._persist_results(build_tools)
        return build_tools

    def _detect_tool_version(self, dir: Path, tool: str) -> Optional[str]:
        self.logger.debug(f"Detecting tool version for {tool} in {dir}")
        handlers = {
            'Poetry': self._get_poetry_version,
            'Pipenv': self._get_pipenv_version,
            'Setuptools': self._get_setuptools_version
        }
        version = handlers.get(tool, lambda _: None)(dir)
        self.logger.debug(f"Detected tool version for {tool}: {version}")
        return version

    def _detect_python_version(self, dir: Path, tool: str) -> Optional[str]:
        self.logger.debug(f"Detecting Python version for {tool} in {dir}")
        handlers = {
            'Poetry': self._get_poetry_py_version,
            'Pipenv': self._get_pipenv_py_version,
            'Setuptools': self._get_setuptools_py_version
        }
        version = handlers.get(tool, lambda _: None)(dir)
        self.logger.debug(f"Detected Python version for {tool}: {version}")
        return version

    def _persist_results(self, build_tools: set):
        self.logger.debug("Persisting build tool analysis results to the database")
        with Session() as session:
            if build_tools:
                stmt = insert(BuildTool).values(list(build_tools))
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['repo_id', 'tool', 'tool_version', 'runtime_version']
                )
                session.execute(stmt)
            session.commit()
            self.logger.debug("Database commit successful")

    def _detect_poetry(self, path: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Detecting Poetry configuration in {path}")
            content = path.read_text(encoding='utf-8')
            return 'Poetry' if '[tool.poetry]' in content else None
        except Exception as e:
            self.logger.debug(f"Failed to detect Poetry: {e}")
            return None

    def _get_poetry_py_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Python version from Poetry configuration in {dir / 'pyproject.toml'}")
            content = (dir / 'pyproject.toml').read_text(encoding='utf-8')
            match = re.search(r'python\s*=\s*"([^"]+)"', content)
            version = match.group(1) if match else None
            self.logger.debug(f"Poetry Python version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Poetry Python version: {e}")
            return None

    def _get_poetry_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Poetry version from {dir / 'poetry.lock'}")
            content = (dir / 'poetry.lock').read_text(encoding='utf-8')
            match = re.search(r'poetry-version\s*=\s*"([^"]+)"', content)
            version = match.group(1) if match else None
            self.logger.debug(f"Poetry version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Poetry version: {e}")
            return None

    def _get_pipenv_py_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Python version from Pipenv configuration in {dir / 'Pipfile'}")
            content = (dir / 'Pipfile').read_text(encoding='utf-8')
            match = re.search(r'python_version\s*=\s*"([^"]+)"', content)
            version = match.group(1) if match else None
            self.logger.debug(f"Pipenv Python version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Pipenv Python version: {e}")
            return None

    def _get_pipenv_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Pipenv version from {dir / 'Pipfile.lock'}")
            content = (dir / 'Pipfile.lock').read_text(encoding='utf-8')
            data = json.loads(content)
            version = data.get('_meta', {}).get('requires', {}).get('pip_version')
            self.logger.debug(f"Pipenv version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Pipenv version: {e}")
            return None

    def _get_setuptools_py_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Python version from Setuptools configuration in {dir / 'setup.py'}")
            content = (dir / 'setup.py').read_text(encoding='utf-8')
            match = re.search(r'python_requires\s*=\s*["\']([^"\']+)', content)
            version = match.group(1) if match else None
            self.logger.debug(f"Setuptools Python version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Setuptools Python version: {e}")
            return None

    def _get_setuptools_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Setuptools version from {dir / 'setup.py'}")
            content = (dir / 'setup.py').read_text(encoding='utf-8')
            match = re.search(r'setuptools>=([\d.]+)', content)
            version = match.group(1) if match else None
            self.logger.debug(f"Setuptools version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Setuptools version: {e}")
            return None

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    test_dir = Path("/home/fadzi/tools/python_projects/python_security")
    test_repo = {
        "repo_id": "gbleaney/python_security",
        "repo_dir": test_dir
    }

    analyzer = PythonBuildToolAnalyzer(
        logger=logging.getLogger("PythonBuildToolAnalyzer"),
        run_id="dummy_run_id"
    )

    try:
        build_tools = analyzer.run_analysis(test_dir, test_repo)
        print(f"Analysis successful: Found {len(build_tools)} build tools")
    except Exception as e:
        print(f"Analysis failed: {str(e)}")