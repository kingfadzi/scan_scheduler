import re
import sys
import logging
import subprocess
import venv
import json
from pathlib import Path
from typing import List, Optional, ClassVar

from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger
from sqlalchemy.dialects.postgresql import insert

class PythonDependencyAnalyzer(BaseLogger):
    USE_VENV_FALLBACK: ClassVar[bool] = False
    VERSION_PATTERN = re.compile(
        r"^(?P<name>[\w.-]+)"
        r"(?P<specifiers>(?:==|>=|<=|~=|!=|<|>|===|@)\S+)?"
    )

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.utils = Utils(logger=logger)
        self.logger.debug("Initialized PythonDependencyAnalyzer (dependencies only)")

    @analyze_execution(
        session_factory=Session,
        stage="Python Dependency Analysis",
        require_language=["Python", "Jupyter Notebook"]
    )
    def run_analysis(self, repo_dir, repo):
        self.logger.debug(f"Starting dependency analysis on repo {repo.get('repo_id', 'unknown')} in {repo_dir}")
        root_dir = Path(repo_dir)
        self.logger.debug(f"Resolved repository directory: {root_dir.resolve()}")
        all_dependencies = []

        try:
            # Fast path: Direct requirements.txt parsing
            req_files = self._find_requirements_files(root_dir)
            self.logger.debug(f"Found {len(req_files)} requirements.txt files")
            for req_file in req_files:
                self.logger.debug(f"Parsing requirements file: {req_file}")
                deps = self._parse_requirements_file(req_file, repo)
                self.logger.debug(f"Parsed {len(deps)} dependencies from {req_file}")
                all_dependencies.extend(deps)
            
            # Fallback path: Venv-based analysis if no requirements file found
            if not req_files and self.USE_VENV_FALLBACK:
                self.logger.debug("No requirements.txt files found, using venv fallback analysis")
                venv_deps = self._venv_fallback_analysis(root_dir, repo)
                self.logger.debug(f"Venv fallback analysis found {len(venv_deps)} dependencies")
                all_dependencies.extend(venv_deps)

            self.logger.debug(f"Persisting {len(all_dependencies)} dependencies")
            self._persist_dependencies(all_dependencies)
            return f"Found {len(all_dependencies)} dependencies"

        except Exception as e:
            self.logger.exception(f"Analysis failed: {e}")
            raise

    def _find_requirements_files(self, root_dir: Path) -> List[Path]:
        self.logger.debug(f"Searching for requirements.txt files in {root_dir}")
        files = list(root_dir.rglob('requirements.txt'))
        self.logger.debug(f"Found {len(files)} requirements.txt files")
        return files

    def _parse_requirements_file(self, req_file: Path, repo: dict) -> List[BuildTool]:
        dependencies = []
        py_version = self._get_python_version()
        self.logger.debug(f"Using system python version: {py_version} for parsing {req_file}")

        try:
            content = req_file.read_text(encoding='utf-8')
            self.logger.debug(f"Read content from {req_file}")
        except UnicodeDecodeError:
            self.logger.warning(f"Skipping non-text file: {req_file}")
            return []

        for line in content.splitlines():
            original_line = line
            line = line.split('#')[0].strip()
            if not line:
                continue

            # Handle include directives (e.g. -r another_requirements.txt)
            if line.startswith(('-r ', '--requirement ')):
                included = req_file.parent / line.split(' ', 1)[1]
                self.logger.debug(f"Found include directive in {req_file}: including file {included}")
                if included.exists():
                    dependencies.extend(self._parse_requirements_file(included, repo))
                continue

            # Parse package details using the version pattern
            if match := self.VERSION_PATTERN.match(line):
                name = match['name']
                spec = (match['specifiers'] or '').strip()
                version = self._extract_version(spec) if spec else None
                self.logger.debug(f"Parsed dependency from line '{original_line}': name={name}, version={version}")
                dependencies.append(BuildTool(
                    repo_id=repo['repo_id'],
                    tool=name,
                    tool_version=version,
                    runtime_version=py_version
                ))

        return dependencies

    def _venv_fallback_analysis(self, root_dir: Path, repo: dict) -> List[BuildTool]:
        venv_path = root_dir / '.tmp_venv'
        dependencies = []
        try:
            self.logger.info("Starting venv fallback analysis")
            self.logger.debug(f"Creating virtual environment at {venv_path}")
            venv.create(venv_path, with_pip=True)
            py_version = self._get_venv_python_version(venv_path)
            self.logger.debug(f"Virtual environment python version: {py_version}")

            # Optionally install project dependencies if a setup.py exists
            if (root_dir / "setup.py").exists():
                self.logger.debug("Found setup.py, installing project dependencies with pip")
                pip = venv_path / 'bin' / 'pip'
                subprocess.run([str(pip), 'install', '.'], cwd=str(root_dir), check=True, capture_output=True)
            else:
                self.logger.debug("No setup.py found, skipping installation")

            frozen_file = self._freeze_requirements(venv_path, root_dir)
            self.logger.debug(f"Parsing frozen requirements from {frozen_file}")
            for line in frozen_file.read_text().splitlines():
                if line.strip() and not line.startswith('-e '):
                    pkg_name = line.split('==')[0].split(' @ ')[0]
                    pkg_version = self._extract_version(line)
                    self.logger.debug(f"Found frozen dependency: {pkg_name} with version: {pkg_version}")
                    dependencies.append(BuildTool(
                        repo_id=repo['repo_id'],
                        tool=pkg_name,
                        tool_version=pkg_version,
                        runtime_version=py_version
                    ))
            return dependencies
        finally:
            self._cleanup_venv(venv_path)

    def _freeze_requirements(self, venv_path: Path, root_dir: Path) -> Path:
        pip = venv_path / 'bin' / 'pip'
        frozen_file = root_dir / 'frozen_requirements.txt'
        self.logger.debug(f"Freezing requirements using pip at {pip}")
        result = subprocess.run(
            [str(pip), 'freeze', '--all'],
            cwd=str(root_dir),
            check=True,
            capture_output=True,
            text=True
        )
        frozen_file.write_text(result.stdout)
        self.logger.debug(f"Frozen requirements written to {frozen_file}")
        return frozen_file

    def _persist_dependencies(self, dependencies: List[BuildTool]):
        self.logger.debug("Persisting dependency analysis results to the database")
        with Session() as session:
            if dependencies:
                self.logger.debug(f"Persisting {len(dependencies)} dependencies")
                session.bulk_save_objects(dependencies)
            session.commit()
            self.logger.debug("Database commit successful")

    def _extract_version(self, spec: str) -> Optional[str]:
        patterns = [
            r'==([\w.]+)',          # Standard version
            r'/([\w.]+)\.(tar|zip)', # Archive versions
            r'@ .+/([\w.]+)\.'      # Direct URLs
        ]
        for pattern in patterns:
            if match := re.search(pattern, spec):
                version = match.group(1)
                self.logger.debug(f"Extracted version '{version}' using pattern '{pattern}' from spec '{spec}'")
                return version
        self.logger.debug(f"No version extracted from spec '{spec}'")
        return None

    def _get_python_version(self) -> Optional[str]:
        match = re.search(r'\d+\.\d+\.\d+', sys.version)
        version = match.group() if match else None
        self.logger.debug(f"System python version detected: {version}")
        return version

    def _get_venv_python_version(self, venv_path: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                [venv_path / 'bin' / 'python', '-V'],
                capture_output=True,
                text=True,
                check=True
            )
            match = re.search(r'\d+\.\d+\.\d+', result.stderr or result.stdout)
            version = match.group() if match else None
            self.logger.debug(f"Virtual environment python version detected: {version}")
            return version
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error detecting venv python version: {e}")
            return None

    def _cleanup_venv(self, venv_path: Path):
        try:
            if venv_path.exists():
                self.logger.debug(f"Cleaning up virtual environment at {venv_path}")
                self.utils.remove_directory(venv_path, retries=3)
        except Exception as e:
            self.logger.error(f"Venv cleanup failed: {str(e)}")

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
    analyzer = PythonDependencyAnalyzer(
        logger=logging.getLogger("PythonDependencyAnalyzer"),
        run_id="dummy_run_id"
    )
    try:
        result = analyzer.run_analysis(test_dir, test_repo)
        print(f"Analysis successful: {result}")
    except Exception as e:
        print(f"Analysis failed: {str(e)}")