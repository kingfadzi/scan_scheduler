import json
import os
import re
import logging
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert

from shared.language_required_decorator import language_required
from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger

class GoBuildToolAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.version_regex = re.compile(r'go (\d+\.\d+(?:\.\d+)?)')
        self.utils = Utils(logger=self.logger)

    @analyze_execution(
      session_factory=Session,
      stage="Go Build Analysis",
      require_language="go"
    )
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting Go analysis for {repo['repo_id']}")

        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        if 'Go' not in repo_languages:
            msg = f"Skipping non-Go repo {repo['repo_id']}"
            self.logger.info(msg)
            return msg

        build_tool = self.detect_build_tool(repo_dir)
        go_version = self.detect_go_version(repo_dir)
        tool_version = self.detect_tool_version(repo_dir, build_tool)

        self.utils.persist_build_tool(build_tool, repo["repo_id"], tool_version, go_version)

        return json.dumps({
            "repo_id": repo['repo_id'],
            "tool": build_tool,
            "tool_version": tool_version,
            "runtime_version": go_version
        })

    def detect_build_tool(self, repo_dir):

        tool_files = [
            ('go.mod', 'Go Modules'),
            ('Gopkg.toml', 'dep'),
            ('glide.yaml', 'glide'),
            ('vendor/vendor.json', 'govendor')
        ]

        for file_name, tool in tool_files:
            if (Path(repo_dir) / file_name).exists():
                return tool
        return "Go Modules" if self._has_go_files(repo_dir) else None

    def _has_go_files(self, repo_dir):

        for root, _, files in os.walk(repo_dir):
            if any(f.endswith('.go') for f in files):
                return True
        return False

    def detect_go_version(self, repo_dir):

        go_mod = Path(repo_dir) / 'go.mod'
        if go_mod.exists():
            try:
                with open(go_mod, 'r') as f:
                    for line in f:
                        if line.startswith('go '):
                            return line.split()[-1].strip()
            except Exception as e:
                self.logger.error(f"Error reading go.mod: {e}")

        go_version_file = Path(repo_dir) / '.go-version'
        if go_version_file.exists():
            try:
                with open(go_version_file, 'r') as f:
                    return f.read().strip()
            except Exception as e:
                self.logger.error(f"Error reading .go-version: {e}")

        return "Unknown"

    def detect_tool_version(self, repo_dir, build_tool):

        version_methods = {
            'dep': lambda: self._parse_dep_version(repo_dir),
            'glide': lambda: self._parse_glide_version(repo_dir),
            'Go Modules': lambda: self._parse_go_mod_version(repo_dir)
        }
        return version_methods.get(build_tool, lambda: "Unknown")()

    def _parse_dep_version(self, repo_dir):

        lock_file = Path(repo_dir) / 'Gopkg.lock'
        try:
            with open(lock_file, 'r') as f:
                for line in f:
                    if line.startswith('version = '):
                        return line.split('=')[-1].strip().strip('"')
        except Exception as e:
            self.logger.error(f"Error reading Gopkg.lock: {e}")
        return "Unknown"

    def _parse_glide_version(self, repo_dir):
        """Get Glide version from glide.yaml"""
        glide_file = Path(repo_dir) / 'glide.yaml'
        try:
            with open(glide_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('version:'):
                        return line.split(':')[-1].strip()
        except Exception as e:
            self.logger.error(f"Error reading glide.yaml: {e}")
        return "Unknown"

    def _parse_go_mod_version(self, repo_dir):

        return "Unknown"

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    test_repo = MockRepo("go-test-456", "example-go-repo")
    test_repo_dir = "/path/to/go/project"

    analyzer = GoBuildToolAnalyzer()
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
        print("Analysis session closed")
