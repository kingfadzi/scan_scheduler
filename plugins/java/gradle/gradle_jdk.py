import os
from pathlib import Path
import re
import yaml
import json
import logging
from typing import List, Dict, Optional
from sqlalchemy.dialects.postgresql import insert

from shared.language_required_decorator import language_required
from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
from shared.utils import Utils

class GradlejdkAnalyzer(BaseLogger):

    SCRIPT_DIR = Path(__file__).parent.resolve()
    PROJECT_ROOT = SCRIPT_DIR.parent
    CONFIG_DIR = PROJECT_ROOT / 'gradle'

    GRADLE_RULES_FILE = CONFIG_DIR / 'gradle_rules.yaml'
    JDK_MAPPING_FILE = CONFIG_DIR / 'jdk_mapping.yaml'
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea'}


    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

        self.utils = Utils(logger=logger)
        self.rules: List[Dict] = []
        self.jdk_mapping: Dict = {}

    def load_config(self) -> None:
        self.logger.debug("Loading configuration files")
        config_errors = []

        if not self.GRADLE_RULES_FILE.exists():
            config_errors.append(f"Missing rules file: {self.GRADLE_RULES_FILE}")
        if not self.JDK_MAPPING_FILE.exists():
            config_errors.append(f"Missing JDK mapping: {self.JDK_MAPPING_FILE}")

        if config_errors:
            raise FileNotFoundError("\n".join(config_errors))

        try:
            with open(self.GRADLE_RULES_FILE, 'r') as f:
                self.rules = yaml.safe_load(f)['extraction_rules']
            with open(self.JDK_MAPPING_FILE, 'r') as f:
                self.jdk_mapping = yaml.safe_load(f)
            self.logger.info("Configuration files loaded successfully")
        except Exception as e:
            self.logger.error("Config load failed", exc_info=True)
            raise RuntimeError(f"Configuration error: {str(e)}")

    def find_gradle_files(self, root: Path) -> List[Path]:

        self.logger.debug(f"Scanning for Gradle files in: {root}")
        gradle_files = []

        for path in root.rglob('*'):
            if any(part in self.EXCLUDE_DIRS for part in path.parts):
                self.logger.debug(f"Skipping excluded path: {path}")
                continue

            if path.is_file() and self._is_gradle_file(path):
                gradle_files.append(path)
                self.logger.info(f"Found Gradle file: {path.relative_to(root)}")

        self.logger.info(f"Found {len(gradle_files)} Gradle configuration files")
        return sorted(gradle_files, key=lambda p: 0 if 'wrapper' in p.parts else 1)

    def _is_gradle_file(self, path: Path) -> bool:

        return (
            path.parts[-3:] == ('gradle', 'wrapper', 'gradle-wrapper.properties') or
            path.name in {'build.gradle', 'build.gradle.kts',
                         'settings.gradle', 'settings.gradle.kts',
                         'gradle.properties'}
        )

    def extract_version(self, content: str, pattern: str) -> Optional[str]:

        self.logger.debug(f"Applying version pattern: {pattern}")
        try:
            if match := re.search(pattern, content, re.MULTILINE):
                version = match.group(1).split('-')[0]
                self.logger.info(f"Version match found: {version}")
                return version
            self.logger.debug("No version match in content")
        except Exception as e:
            self.logger.error(f"Regex error: {str(e)}", exc_info=True)
        return None

    def find_jdk_version(self, gradle_version: str) -> str:

        self.logger.info(f"Starting JDK lookup for Gradle {gradle_version}")
        parts = gradle_version.split('.')
        lookup_path = []

        while parts:
            lookup_version = '.'.join(parts)
            lookup_path.append(lookup_version)
            self.logger.debug(f"Checking JDK mapping for: {lookup_version}")

            if jdk := self.jdk_mapping.get(lookup_version):
                self.logger.info(f"JDK match found: {jdk} for {lookup_version}")
                return jdk
            parts.pop()

        self.logger.warning(f"No JDK mapping found for Gradle {gradle_version}")
        self.logger.debug(f"Checked versions: {', '.join(lookup_path)}")
        return "JDK version unknown"


    @language_required("java")
    @analyze_execution(session_factory=Session, stage="Gradle JDK Analysis")
    def run_analysis(self, repo_dir, repo):

        self.logger.info(f"Starting analysis for repository: {repo_dir}")

        repo_dir = os.path.abspath(repo_dir)
        if not os.path.exists(repo_dir):
            raise FileNotFoundError(f"Directory not found: {repo_dir}")
        repo_path = Path(repo_dir)

        try:

            self.load_config()
            found_files = self.find_gradle_files(repo_path)

            if not found_files:
                self.logger.warning("No Gradle configuration files found")
                return json.dumps({
                    "gradle_project": False,
                    "repo_id": repo['repo_id'],
                    "status": "success"
                }, ensure_ascii=False)

            gradle_version = None
            for file in found_files:
                try:
                    content = file.read_text(encoding='utf-8')
                    self.logger.debug(f"Analyzing file: {file.relative_to(repo_path)}")

                    for rule in self.rules:
                        if file.match(rule['file']):
                            if version := self.extract_version(content, rule['regex']):
                                gradle_version = version
                                self.logger.info(f"Final Gradle version: {gradle_version}")
                                break
                    if gradle_version:
                        break
                except Exception as e:
                    self.logger.error(f"File analysis failed: {file}", exc_info=True)
                    continue

            if not gradle_version:
                error_msg = [
                    "Gradle version detection failed in:",
                    *[f"  - {f.relative_to(repo_path)}" for f in found_files]
                ]
                raise RuntimeError("\n".join(error_msg))

            jdk_version = self.find_jdk_version(gradle_version)
            self.logger.info(f"Final JDK determination: {jdk_version}")

            self.utils.persist_build_tool("gradle", repo["repo_id"], gradle_version, jdk_version)

            return json.dumps({
                "gradle_project": True,
                "gradle_version": gradle_version,
                "jdk_version": jdk_version,
                "repo_id": repo['repo_id'],
                "status": "success"
            }, ensure_ascii=False)

        except Exception as e:
            self.logger.error("Analysis failed", exc_info=True)
            raise

if __name__ == "__main__":

    repo_dir = "/Users/fadzi/tools/gradle_projects/gradle-simple"
    repo_id = "commjoen/wrongsecrets"
    repo_slug = "gradle-example"

    analyzer = GradlejdkAnalyzer()

    repo = {
        "repo_id": repo_id,
        "repo_slug": repo_slug,
        "repo_name": repo_slug
    }

    session = Session()

    try:
        analyzer.logger.info(f"Starting analysis for {repo['repo_slug']}")
        result = analyzer.run_analysis(repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Analysis completed successfully")
    except Exception as e:
        analyzer.logger.error(f"Analysis failed: {e}")
    finally:
        session.close()
        analyzer.logger.info("Database session closed")
