import re
import sys
import logging
import subprocess
import venv
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
        r"(?:\[[\w,]+\])?"     # Extras
        r"(?P<specifiers>(?:==|>=|<=|~=|!=|<|>|===|@)\S+)?"  # Versions/URLs
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

    @analyze_execution(
        session_factory=Session,
        stage="Python Dependency Analysis",
        require_language=["Python", "Jupyter Notebook"]
    )
    def run_analysis(self, repo_dir, repo):
        root_dir = Path(repo_dir)
        all_dependencies = []
        build_tools = set()

        try:
            # Fast path: Direct requirements.txt parsing
            req_files = self._find_requirements_files(root_dir)
            
            for req_file in req_files:
                deps = self._parse_requirements_file(req_file, repo)
                all_dependencies.extend(deps)
                
                if tool_data := self._detect_build_tool_info(req_file.parent, repo):
                    build_tools.add(tool_data)

            # Fallback path: Venv-based analysis
            if not req_files and self.USE_VENV_FALLBACK:
                venv_deps = self._venv_fallback_analysis(root_dir, repo)
                all_dependencies.extend(venv_deps)

            self._persist_results(all_dependencies, build_tools)
            return f"Found {len(all_dependencies)} dependencies"

        except Exception as e:
            self.logger.exception(f"Analysis failed: {e}")
            raise

    def _find_requirements_files(self, root_dir: Path) -> List[Path]:
        return list(root_dir.rglob('requirements.txt'))

    def _parse_requirements_file(self, req_file: Path, repo: dict) -> List[BuildTool]:
        dependencies = []
        py_version = self._get_python_version()

        try:
            content = req_file.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            self.logger.warning(f"Skipping non-text file: {req_file}")
            return []

        for line in content.splitlines():
            line = line.split('#')[0].strip()
            if not line:
                continue

            # Handle includes
            if line.startswith(('-r ', '--requirement ')):
                included = req_file.parent / line.split(' ', 1)[1]
                if included.exists():
                    dependencies.extend(self._parse_requirements_file(included, repo))
                continue

            # Parse package details
            if match := self.VERSION_PATTERN.match(line):
                name = match['name']
                spec = (match['specifiers'] or '').strip()
                version = self._extract_version(spec) if spec else None

                dependencies.append(BuildTool(
                    repo_id=repo['repo_id'],
                    tool=name,
                    tool_version=version,
                    runtime_version=py_version
                ))

        return dependencies

    def _detect_build_tool_info(self, directory: Path, repo: dict) -> Optional[Dict]:
        for file_name, detector in self.build_tool_detectors:
            target = directory / file_name
            if not target.exists():
                continue

            tool_name = detector(target) if callable(detector) else detector
            if not tool_name:
                continue

            return {
                'repo_id': repo['repo_id'],
                'tool': tool_name,
                'tool_version': self._detect_tool_version(directory, tool_name),
                'runtime_version': self._detect_python_version(directory, tool_name)
            }
        return None

    def _venv_fallback_analysis(self, root_dir: Path, repo: dict) -> List[BuildTool]:
        venv_path = root_dir / '.tmp_venv'
        dependencies = []
        
        try:
            self.logger.info("Starting venv fallback analysis")
            venv.create(venv_path, with_pip=True)
            py_version = self._get_venv_python_version(venv_path)
            
            self._install_dependencies(venv_path, root_dir)
            frozen_file = self._freeze_requirements(venv_path, root_dir)
            
            dependencies = [
                BuildTool(
                    repo_id=repo['repo_id'],
                    tool=line.split('==')[0].split(' @ ')[0],
                    tool_version=self._extract_version(line),
                    runtime_version=py_version
                )
                for line in frozen_file.read_text().splitlines()
                if line.strip() and not line.startswith('-e ')
            ]
            
            return dependencies
            
        finally:
            self._cleanup_venv(venv_path)

    def _install_dependencies(self, venv_path: Path, root_dir: Path):
        pip = venv_path / 'bin' / 'pip'
        
        # Install build tools
        subprocess.run(
            [str(pip), 'install', 'poetry', 'pipenv', 'setuptools'],
            cwd=str(root_dir),
            check=True,
            capture_output=True
        )
        
        # Install project dependencies
        if build_tool := self._detect_primary_build_tool(root_dir):
            self._install_with_build_tool(pip, root_dir, build_tool)
        else:
            self.logger.warning("No build tool detected, skipping installation")

    def _detect_primary_build_tool(self, root_dir: Path) -> Optional[str]:
        for file_name, detector in self.build_tool_detectors:
            target = root_dir / file_name
            if target.exists():
                return detector(target) if callable(detector) else detector
        return None

    def _install_with_build_tool(self, pip: Path, root_dir: Path, tool: str):
        commands = {
            'Poetry': [str(pip), 'run', 'poetry', 'install', '--no-root'],
            'Pipenv': [str(pip), 'run', 'pipenv', 'install', '--deploy'],
            'Setuptools': [str(pip), 'install', '.']
        }
        
        if cmd := commands.get(tool):
            subprocess.run(cmd, cwd=str(root_dir), check=True, capture_output=True)

    def _freeze_requirements(self, venv_path: Path, root_dir: Path) -> Path:
        pip = venv_path / 'bin' / 'pip'
        frozen_file = root_dir / 'frozen_requirements.txt'
        
        result = subprocess.run(
            [str(pip), 'freeze', '--all'],
            cwd=str(root_dir),
            check=True,
            capture_output=True,
            text=True
        )
        frozen_file.write_text(result.stdout)
        return frozen_file

    def _persist_results(self, dependencies: List[BuildTool], build_tools: set):
        with Session() as session:
            # Persist dependencies
            if dependencies:
                session.bulk_save_objects(dependencies)
            
            # Persist build tools
            if build_tools:
                stmt = insert(BuildTool).values(list(build_tools))
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=['repo_id', 'tool', 'tool_version', 'runtime_version']
                )
                session.execute(stmt)
            
            session.commit()

    def _get_python_version(self) -> Optional[str]:
        match = re.search(r'\d+\.\d+\.\d+', sys.version)
        return match.group() if match else None

    def _get_venv_python_version(self, venv_path: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                [venv_path / 'bin' / 'python', '-V'],
                capture_output=True,
                text=True,
                check=True
            )
            match = re.search(r'\d+\.\d+\.\d+', result.stderr or result.stdout)
            return match.group() if match else None
        except subprocess.CalledProcessError:
            return None

    def _cleanup_venv(self, venv_path: Path):
        try:
            if venv_path.exists():
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
                return match.group(1)
        return None

    def _detect_poetry(self, path: Path) -> Optional[str]:
        try:
            content = (path / 'pyproject.toml').read_text(encoding='utf-8')
            return 'Poetry' if '[tool.poetry]' in content else None
        except Exception:
            return None

    def _detect_python_version(self, dir: Path, tool: str) -> Optional[str]:
        handlers = {
            'Poetry': self._get_poetry_py_version,
            'Pipenv': self._get_pipenv_py_version,
            'Setuptools': self._get_setuptools_py_version
        }
        return handlers.get(tool, lambda _: None)(dir)

    def _detect_tool_version(self, dir: Path, tool: str) -> Optional[str]:
        handlers = {
            'Poetry': self._get_poetry_version,
            'Pipenv': self._get_pipenv_version,
            'Setuptools': self._get_setuptools_version
        }
        return handlers.get(tool, lambda _: None)(dir)

    def _get_poetry_py_version(self, dir: Path) -> Optional[str]:
        try:
            content = (dir / 'pyproject.toml').read_text(encoding='utf-8')
            match = re.search(r'python\s*=\s*"([^"]+)"', content)
            return match.group(1) if match else None
        except Exception:
            return None

    def _get_poetry_version(self, dir: Path) -> Optional[str]:
        try:
            content = (dir / 'poetry.lock').read_text(encoding='utf-8')
            match = re.search(r'poetry-version\s*=\s*"([^"]+)"', content)
            return match.group(1) if match else None
        except Exception:
            return None

    def _get_pipenv_py_version(self, dir: Path) -> Optional[str]:
        try:
            content = (dir / 'Pipfile').read_text(encoding='utf-8')
            match = re.search(r'python_version\s*=\s*"([^"]+)"', content)
            return match.group(1) if match else None
        except Exception:
            return None

    def _get_pipenv_version(self, dir: Path) -> Optional[str]:
        try:
            content = (dir / 'Pipfile.lock').read_text(encoding='utf-8')
            data = json.loads(content)
            return data.get('_meta', {}).get('requires', {}).get('pip_version')
        except Exception:
            return None

    def _get_setuptools_py_version(self, dir: Path) -> Optional[str]:
        try:
            content = (dir / 'setup.py').read_text(encoding='utf-8')
            match = re.search(r'python_requires\s*=\s*["\']([^"\']+)', content)
            return match.group(1) if match else None
        except Exception:
            return None

    def _get_setuptools_version(self, dir: Path) -> Optional[str]:
        try:
            content = (dir / 'setup.py').read_text(encoding='utf-8')
            match = re.search(r'setuptools>=([\d.]+)', content)
            return match.group(1) if match else None
        except Exception:
            return None

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    class MockRepo:
        def __init__(self, repo_id, repo_dir):
            self.repo_id = repo_id
            self.repo_dir = repo_dir

    test_dir = Path("/path/to/test/repo")
    test_repo = MockRepo("test_repo", test_dir)
    
    analyzer = PythonBuildToolAnalyzer()
    try:
        result = analyzer.run_analysis(test_dir, test_repo)
        print(f"Analysis successful: {result}")
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
