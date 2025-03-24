import json
import re
import logging
import os
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert

from shared.language_required_decorator import language_required
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
        stage="Python Build Tool Analysis", 
        require_language=["Python", "Jupyter Notebook"] 
    )
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting Python build tool analysis for {repo['repo_id']}")
        results = []

        if not self._validate_repo(repo):
            return json.dumps({"status": "skipped", "reason": "Not a Python project"})

        for root, dirs, files in os.walk(repo_dir):
            current_dir = Path(root)
            relative_path = current_dir.relative_to(repo_dir)
            
            self.logger.debug(f"Scanning directory: {relative_path}")
            
            build_tool = self._detect_build_tool(current_dir)
            if not build_tool:
                continue
                
            python_version = self._detect_python_version(current_dir, build_tool)
            tool_version = self._detect_tool_version(current_dir, build_tool)
            
            self.logger.info(f"Found {build_tool} in {relative_path}")
            self._persist_finding(repo, build_tool, python_version, tool_version, relative_path)
            
            results.append({
                "directory": str(relative_path),
                "build_tool": build_tool,
                "tool_version": tool_version,
                "python_version": python_version
            })

        return json.dumps({
            "repo_id": repo['repo_id'],
            "findings": results,
            "total_findings": len(results)
        }, indent=2)

    def _validate_repo(self, repo):
        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        return 'Python' in repo_languages

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

    def _persist_finding(self, repo, tool, py_ver, tool_ver, rel_path):
        self.utils.persist_build_tool(
            tool_name=tool,
            repo_id=repo["repo_id"],
            tool_version=tool_ver,
            runtime_version=py_ver,
            subdirectory=str(rel_path)
        )

    # Version detection methods (kept as in original but adjusted for directory parameter)
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