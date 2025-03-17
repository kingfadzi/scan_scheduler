#!/usr/bin/env python3
from pathlib import Path
import re
import yaml
import json
import logging
from typing import List, Dict
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import Session, BuildTool
from modular.shared.execution_decorator import analyze_execution
from modular.shared.base_logger import BaseLogger
from modular.shared.utils import Utils

class GradlejdkAnalyzer(BaseLogger):
    # Path configuration
    SCRIPT_DIR = Path(__file__).parent.resolve()
    PROJECT_ROOT = SCRIPT_DIR.parent
    CONFIG_DIR = PROJECT_ROOT / 'gradle'
    
    GRADLE_RULES_FILE = CONFIG_DIR / 'gradle_rules.yaml'
    JDK_MAPPING_FILE = CONFIG_DIR / 'jdk_mapping.yaml'
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea'}

    def __init__(self, logger=None):
        super().__init__()
        if logger is None:
            self.logger = self.get_logger("GradlejdkAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)
        self.utils = Utils(logger=logger)
        self.rules: List[Dict] = []
        self.jdk_mapping: Dict = {}

    def load_config(self) -> None:
        """Load and validate configuration files from package"""
        config_errors = []
        if not self.GRADLE_RULES_FILE.exists():
            config_errors.append(f"Missing rules file at {self.GRADLE_RULES_FILE}")
        if not self.JDK_MAPPING_FILE.exists():
            config_errors.append(f"Missing JDK mapping at {self.JDK_MAPPING_FILE}")
        if config_errors:
            raise FileNotFoundError("\n".join(config_errors))
        
        try:
            with open(self.GRADLE_RULES_FILE, 'r') as f:
                self.rules = yaml.safe_load(f)['extraction_rules']
            with open(self.JDK_MAPPING_FILE, 'r') as f:
                self.jdk_mapping = yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {str(e)}")

    def find_gradle_files(self, root: Path) -> List[Path]:
        """Locate Gradle configuration files with exclusion patterns"""
        gradle_files = []
        
        for path in root.rglob('*'):
            if any(part in self.EXCLUDE_DIRS for part in path.parts):
                self.logger.debug(f"Skipping excluded path: {path}")
                continue
                
            if path.is_file() and self._is_gradle_file(path):
                gradle_files.append(path)
                self.logger.debug(f"Found Gradle file: {path}")

        return sorted(gradle_files, key=lambda p: 0 if 'wrapper' in p.parts else 1)

    def _is_gradle_file(self, path: Path) -> bool:
        """Check if file is a Gradle configuration file"""
        return (
            path.parts[-3:] == ('gradle', 'wrapper', 'gradle-wrapper.properties') or
            path.name in {'build.gradle', 'build.gradle.kts',
                         'settings.gradle', 'settings.gradle.kts',
                         'gradle.properties'}
        )

    def extract_version(self, content: str, pattern: str) -> Optional[str]:
        """Extract version using regex pattern"""
        try:
            self.logger.debug(f"Applying regex: {pattern}")
            if match := re.search(pattern, content, re.MULTILINE):
                version = match.group(1).split('-')[0]
                self.logger.debug(f"Matched version: {version}")
                return version
        except Exception as e:
            self.logger.error(f"Regex error: {str(e)}")
        return None

    def find_jdk_version(self, gradle_version: str) -> str:
        """Determine compatible JDK version using hierarchical lookup"""
        parts = gradle_version.split('.')
        while parts:
            lookup = '.'.join(parts)
            if jdk := self.jdk_mapping.get(lookup):
                return jdk
            parts.pop()
        return "JDK version unknown"

    def _persist_results(self, session, repo, gradle_version: str, java_version: str) -> None:
        """Persist results to database with UPSERT operation"""
        try:
            stmt = insert(BuildTool).values(
                repo_id=repo.repo_id,
                tool="Gradle",
                tool_version=gradle_version,
                runtime_version=java_version,
            ).on_conflict_do_update(
                index_elements=["repo_id", "tool"],
                set_={
                    "tool_version": gradle_version,
                    "runtime_version": java_version,
                }
            )
            session.execute(stmt)
            session.commit()
            self.logger.info(f"Persisted results for {repo.repo_slug}")
        except Exception as e:
            self.logger.exception(f"Persistence failed: {e}")
            raise RuntimeError("Database operation failed") from e

    @analyze_execution(session_factory=Session, stage="Gradle JDK Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        """Main analysis workflow with execution tracking"""
        repo_path = Path(repo_dir).resolve()
        if not repo_path.exists():
            raise ValueError(f"Invalid repository path: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"Path is not a directory: {repo_path}")

        self.load_config()
        found_files = self.find_gradle_files(repo_path)
        
        if not found_files:
            raise RuntimeError("No Gradle configuration files found")

        gradle_version = None
        for file in found_files:
            try:
                content = file.read_text(encoding='utf-8')
                self.logger.debug(f"Processing: {file.relative_to(repo_path)}")
                
                sample_content = content[:200].replace('\n', ' ')
                self.logger.debug(f"Content sample: {sample_content}...")

                for rule in self.rules:
                    if file.match(rule['file']):
                        if version := self.extract_version(content, rule['regex']):
                            self.logger.info(f"Detected Gradle {version}")
                            gradle_version = version
                            break
                if gradle_version:
                    break
            except Exception as e:
                self.logger.error(f"File error: {str(e)}")

        if not gradle_version:
            error_msg = [
                "Gradle version detection failed. Scanned files:",
                *[f"  - {f.relative_to(repo_path)}" for f in found_files]
            ]
            raise RuntimeError("\n".join(error_msg))
        
        jdk_version = self.find_jdk_version(gradle_version)
        self._persist_results(session, repo, gradle_version, jdk_version)
        
        return json.dumps({
            "gradle_version": gradle_version,
            "jdk_version": jdk_version,
            "repo_id": repo.repo_id,
            "status": "success"
        }, ensure_ascii=False)

if __name__ == "__main__":
    # Standalone execution configuration
    repo_dir = "/tmp/gradle-example"
    repo_id = "example-org/gradle-example"
    repo_slug = "gradle-example"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    # Initialize components
    repo = MockRepo(repo_id, repo_slug)
    session = Session()
    analyzer = GradlejdkAnalyzer()
    analyzer.logger.setLevel(logging.INFO)

    try:
        result_json = analyzer.run_analysis(
            repo_dir=repo_dir,
            repo=repo,
            session=session,
            run_id="STANDALONE_RUN"
        )
        result = json.loads(result_json)
        analyzer.logger.info(f"Analysis succeeded: {result}")
    except Exception as e:
        analyzer.logger.error(f"Analysis failed: {str(e)}")
        session.rollback()
    finally:
        session.close()