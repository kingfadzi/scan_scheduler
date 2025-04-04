import re
import sys
import logging
import subprocess
import venv
import json
from pathlib import Path
from typing import List, Dict, Optional, ClassVar
from sqlalchemy.dialects.postgresql import insert

from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger

class PythonBuildToolAnalyzer(BaseLogger):
    USE_VENV_FALLBACK: ClassVar[bool] = False
    VERSION_PATTERN = re.compile(
        r"^(?P<name>[\w.-]+)"
        r"(?P<specifiers>(?:==|>=|<=|~=|!=|<|>|===|@)\S+)?"
    )

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
        self.logger.debug("Initialized PythonBuildToolAnalyzer")

    @analyze_execution(
        session_factory=Session,
        stage="Python Dependency Analysis",
        require_language=["Python", "Jupyter Notebook"]
    )
    def run_analysis(self, repo_dir, repo):
        self.logger.debug(f"Starting analysis on repo {repo.get('repo_id', 'unknown')} in {repo_dir}")
        root_dir = Path(repo_dir)
        self.logger.debug(f"Resolved repository directory: {root_dir.resolve()}")
        all_dependencies = []
        build_tools = set()

        try:
            # Fast path: Direct requirements.txt parsing
            req_files = self._find_requirements_files(root_dir)
            self.logger.debug(f"Found {len(req_files)} requirements.txt files")

            for req_file in req_files:
                self.logger.debug(f"Parsing requirements file: {req_file}")
                deps = self._parse_requirements_file(req_file, repo)
                self.logger.debug(f"Parsed {len(deps)} dependencies from {req_file}")
                all_dependencies.extend(deps)
                
                tool_data = self._detect_build_tool_info(req_file.parent, repo)
                if tool_data:
                    self.logger.debug(f"Detected build tool info: {tool_data} in {req_file.parent}")
                    build_tools.add(tool_data)

            # Fallback path: Venv-based analysis
            if not req_files and self.USE_VENV_FALLBACK:
                self.logger.debug("No requirements.txt files found, using venv fallback analysis")
                venv_deps = self._venv_fallback_analysis(root_dir, repo)
                self.logger.debug(f"Venv fallback analysis found {len(venv_deps)} dependencies")
                all_dependencies.extend(venv_deps)

            self.logger.debug(f"Persisting {len(all_dependencies)} dependencies and {len(build_tools)} build tools")
            self._persist_results(all_dependencies, build_tools)
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

            # Handle includes
            if line.startswith(('-r ', '--requirement ')):
                included = req_file.parent / line.split(' ', 1)[1]
                self.logger.debug(f"Found include directive in {req_file}: including file {included}")
                if included.exists():
                    dependencies.extend(self._parse_requirements_file(included, repo))
                continue

            # Parse package details
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

    def _detect_build_tool_info(self, directory: Path, repo: dict) -> Optional[Dict]:
        self.logger.debug(f"Detecting build tool info in directory: {directory}")
        for file_name, detector in self.build_tool_detectors:
            target = directory / file_name
            self.logger.debug(f"Checking for {file_name} in {directory}")
            if not target.exists():
                continue

            tool_name = detector(target) if callable(detector) else detector
            if not tool_name:
                self.logger.debug(f"Detector for {file_name} returned no tool")
                continue

            detected_info = {
                'repo_id': repo['repo_id'],
                'tool': tool_name,
                'tool_version': self._detect_tool_version(directory, tool_name),
                'runtime_version': self._detect_python_version(directory, tool_name)
            }
            self.logger.debug(f"Detected build tool info: {detected_info}")
            return detected_info
        return None

    def _venv_fallback_analysis(self, root_dir: Path, repo: dict) -> List[BuildTool]:
        venv_path = root_dir / '.tmp_venv'
        dependencies = []
        
        try:
            self.logger.info("Starting venv fallback analysis")
            self.logger.debug(f"Creating virtual environment at {venv_path}")
            venv.create(venv_path, with_pip=True)
            py_version = self._get_venv_python_version(venv_path)
            self.logger.debug(f"Virtual environment python version: {py_version}")
            
            self._install_dependencies(venv_path, root_dir)
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

    def _install_dependencies(self, venv_path: Path, root_dir: Path):
        pip = venv_path / 'bin' / 'pip'
        self.logger.debug(f"Installing dependencies using pip at {pip}")
        
        # Install build tools
        self.logger.debug("Installing build tools: poetry, pipenv, setuptools")
        subprocess.run(
            [str(pip), 'install', 'poetry', 'pipenv', 'setuptools'],
            cwd=str(root_dir),
            check=True,
            capture_output=True
        )
        
        # Install project dependencies
        build_tool = self._detect_primary_build_tool(root_dir)
        if build_tool:
            self.logger.debug(f"Detected primary build tool: {build_tool}, installing project dependencies")
            self._install_with_build_tool(pip, root_dir, build_tool)
        else:
            self.logger.warning("No build tool detected, skipping installation")

    def _detect_primary_build_tool(self, root_dir: Path) -> Optional[str]:
        self.logger.debug(f"Detecting primary build tool in {root_dir}")
        for file_name, detector in self.build_tool_detectors:
            target = root_dir / file_name
            if target.exists():
                tool = detector(target) if callable(detector) else detector
                self.logger.debug(f"Primary build tool detected: {tool} from file {file_name}")
                return tool
        return None

    def _install_with_build_tool(self, pip: Path, root_dir: Path, tool: str):
        commands = {
            'Poetry': [str(pip), 'run', 'poetry', 'install', '--no-root'],
            'Pipenv': [str(pip), 'run', 'pipenv', 'install', '--deploy'],
            'Setuptools': [str(pip), 'install', '.']
        }
        
        if cmd := commands.get(tool):
            self.logger.debug(f"Installing with {tool} using command: {' '.join(cmd)}")
            subprocess.run(cmd, cwd=str(root_dir), check=True, capture_output=True)
        else:
            self.logger.warning(f"No installation command defined for build tool: {tool}")

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

    def _persist_results(self, dependencies: List[BuildTool], build_tools: set):
        self.logger.debug("Persisting analysis results to the database")
        with Session() as session:
            # Persist dependencies
            if dependencies:
                self.logger.debug(f"Persisting {len(dependencies)} dependencies")
                session.bulk_save_objects(dependencies)
            
            # Persist build tools
            if build_tools:
                self.logger.debug(f"Persisting {len(build_tools)} build tools")
                stmt = insert(BuildTool).values(list(build_tools))
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['repo_id', 'tool', 'tool_version', 'runtime_version']
                )
                session.execute(stmt)
            
            session.commit()
            self.logger.debug("Database commit successful")

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

    def _detect_poetry(self, path: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Detecting Poetry configuration in {path / 'pyproject.toml'}")
            content = (path / 'pyproject.toml').read_text(encoding='utf-8')
            return 'Poetry' if '[tool.poetry]' in content else None
        except Exception as e:
            self.logger.debug(f"Failed to detect Poetry: {e}")
            return None

    def _detect_python_version(self, dir: Path, tool: str) -> Optional[str]:
        self.logger.debug(f"Detecting python version for tool {tool} in directory {dir}")
        handlers = {
            'Poetry': self._get_poetry_py_version,
            'Pipenv': self._get_pipenv_py_version,
            'Setuptools': self._get_setuptools_py_version
        }
        version = handlers.get(tool, lambda _: None)(dir)
        self.logger.debug(f"Detected python version for {tool}: {version}")
        return version

    def _detect_tool_version(self, dir: Path, tool: str) -> Optional[str]:
        self.logger.debug(f"Detecting tool version for {tool} in directory {dir}")
        handlers = {
            'Poetry': self._get_poetry_version,
            'Pipenv': self._get_pipenv_version,
            'Setuptools': self._get_setuptools_version
        }
        version = handlers.get(tool, lambda _: None)(dir)
        self.logger.debug(f"Detected tool version for {tool}: {version}")
        return version

    def _get_poetry_py_version(self, dir: Path) -> Optional[str]:
        try:
            self.logger.debug(f"Extracting Python version from Poetry configuration in {dir / 'pyproject.toml'}")
            content = (dir / 'pyproject.toml').read_text(encoding='utf-8')
            match = re.search(r'python\s*=\s*"([^"]+)"', content)
            version = match.group(1) if match else None
            self.logger.debug(f"Poetry python version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Poetry python version: {e}")
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
            self.logger.debug(f"Pipenv python version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Pipenv python version: {e}")
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
            self.logger.debug(f"Setuptools python version: {version}")
            return version
        except Exception as e:
            self.logger.debug(f"Error reading Setuptools python version: {e}")
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
    
    # Use dictionary instead of a MockRepo class
    test_dir = Path("/home/fadzi/tools/python_projects/python_security")
    test_repo = {
        "repo_id": "gbleaney/python_security",
        "repo_dir": test_dir
    }
    
    # Instantiate with a dummy run ID
    analyzer = PythonBuildToolAnalyzer(
        logger=logging.getLogger("PythonBuildToolAnalyzer"),
        run_id="dummy_run_id"
    )
    
    try:
        result = analyzer.run_analysis(test_dir, test_repo)
        print(f"Analysis successful: {result}")
    except Exception as e:
        print(f"Analysis failed: {str(e)}")