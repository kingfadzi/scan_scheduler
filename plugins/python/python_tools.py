import json
import re
import logging
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert

from shared.language_required_decorator import language_required
from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger

class PythonBuildToolAnalyzer(BaseLogger):
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger or self.get_logger("PythonAnalyzer")
        self.logger.setLevel(logging.DEBUG)
        self.version_pattern = re.compile(r"==(\d+\.\d+\.\d+|\d+\.\d+)")
        self.utils = Utils(logger=logger)

    @language_required("Python")
    @analyze_execution(session_factory=Session, stage="Python Build Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting Python analysis for {repo['repo_id']}")

        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        if 'Python' not in repo_languages:
            msg = f"Skipping non-Python repo {repo['repo_id']}"
            self.logger.info(msg)
            return msg

        build_tool = self.detect_build_tool(repo_dir)
        if not build_tool:
            msg = f"No Python build tool detected for {repo['repo_id']}"
            self.logger.info(msg)
            return msg

        python_version = self.detect_python_version(repo_dir, build_tool)
        tool_version = self.detect_tool_version(repo_dir, build_tool)

        session = Session()

        try:
            session.execute(
                insert(BuildTool).values(
                    repo_id=repo['repo_id'],
                    tool=build_tool,
                    tool_version=tool_version,
                    runtime_version=python_version,
                ).on_conflict_do_update(
                    index_elements=["repo_id", "tool"],
                    set_={
                        "tool_version": tool_version,
                        "runtime_version": python_version,
                    }
                )
            )
            session.commit()
        except Exception as e:
            self.logger.error(f"Database error: {e}")
            session.rollback()
            raise
        finally:
            session.close()

        return json.dumps({
            "repo_id": repo['repo_id'],
            "tool": build_tool,
            "tool_version": tool_version,
            "runtime_version": python_version
        })

    def detect_build_tool(self, repo_dir):
        """Detect build tool through file presence with priority"""
        detection_order = [
            ('poetry.lock', 'Poetry'),
            ('pyproject.toml', self._detect_poetry),
            ('Pipfile.lock', 'Pipenv'),
            ('Pipfile', 'Pipenv'),
            ('requirements.txt', 'pip'),
            ('setup.py', 'Setuptools'),
            ('setup.cfg', 'Setuptools'),
            ('hatch.toml', 'Hatch')
        ]

        for file_name, tool in detection_order:
            path = Path(repo_dir) / file_name
            if path.exists():
                if callable(tool):
                    return tool(path)
                return tool
        return None

    def _detect_poetry(self, toml_path):

        try:
            with open(toml_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if '[tool.poetry]' in content:
                    return 'Poetry'
        except Exception as e:
            self.logger.error(f"Error reading pyproject.toml: {e}")
        return None

    def detect_python_version(self, repo_dir, build_tool):

        version_sources = {
            'Poetry': lambda: self._parse_pyproject_version(repo_dir),
            'Pipenv': lambda: self._parse_pipfile_python(repo_dir),
            'pip': lambda: self._parse_runtime_file(repo_dir),
            'Setuptools': lambda: self._parse_setup_py_python(repo_dir)
        }

        return version_sources.get(build_tool, lambda: "Unknown")()

    def detect_tool_version(self, repo_dir, build_tool):

        version_methods = {
            'Poetry': lambda: self._parse_poetry_version(repo_dir),
            'Pipenv': lambda: self._parse_pipfile_version(repo_dir),
            'pip': lambda: self._parse_pip_version(repo_dir),
            'Setuptools': lambda: self._parse_setuptools_version(repo_dir)
        }

        return version_methods.get(build_tool, lambda: "Unknown")()

    def _parse_pyproject_version(self, repo_dir):

        path = Path(repo_dir) / 'pyproject.toml'
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('python = '):
                        return line.split('=')[-1].strip().strip('"\'')
        except Exception as e:
            self.logger.error(f"Error parsing pyproject.toml: {e}")
        return "Unknown"

    def _parse_poetry_version(self, repo_dir):

        path = Path(repo_dir) / 'poetry.lock'
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('metadata'):
                        next_line = next(f).strip()
                        if 'poetry-version' in next_line:
                            return next_line.split('=')[-1].strip().strip('"')
        except (StopIteration, FileNotFoundError):
            pass
        return "Unknown"

    def _parse_pipfile_python(self, repo_dir):

        path = Path(repo_dir) / 'Pipfile'
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('python_version'):
                        return line.split('=')[-1].strip().strip('"')
        except Exception as e:
            self.logger.error(f"Error parsing Pipfile: {e}")
        return "Unknown"

    def _parse_pipfile_version(self, repo_dir):

        path = Path(repo_dir) / 'Pipfile.lock'
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('_meta', {}).get('requires', {}).get('pip_version')
        except (json.JSONDecodeError, FileNotFoundError):
            return "Unknown"

    def _parse_pip_version(self, repo_dir):

        path = Path(repo_dir) / 'requirements.txt'
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.partition('#')[0].strip()
                    if line.startswith('pip=='):
                        return self.version_pattern.search(line).group(1)
        except Exception as e:
            self.logger.error(f"Error parsing requirements.txt: {e}")
        return "Unknown"

    def _parse_setuptools_version(self, repo_dir):

        setup_py = Path(repo_dir) / 'setup.py'
        try:
            with open(setup_py, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'setup_requires\s*=\s*\[([^\]]*)\]', content)
                if match:
                    return re.search(r'setuptools(?:==|\s+)(\d+\.\d+\.?\d*)', match.group(1)).group(1)
        except FileNotFoundError:
            pass

        setup_cfg = Path(repo_dir) / 'setup.cfg'
        try:
            with open(setup_cfg, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('setup_requires'):
                        return re.search(r'setuptools(?:==|\s+)(\d+\.\d+\.?\d*)', line).group(1)
        except FileNotFoundError:
            pass

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
            self.repo_name = repo_slug


    test_repo = MockRepo("python-test-123", "example-python-repo")
    test_repo_dir = "/path/to/your/python/project"  # Replace with actual path

    analyzer = PythonBuildToolAnalyzer()
    session = Session()

    try:

        result = analyzer.run_analysis(
            repo_dir=test_repo_dir,
            repo=test_repo,
            session=session
        )


        print("\nAnalysis Results:")
        print(json.dumps(json.loads(result), indent=2))

    except Exception as e:
        print(f"\nAnalysis failed: {str(e)}")
    finally:
        session.close()
        print("\nAnalysis session closed")
