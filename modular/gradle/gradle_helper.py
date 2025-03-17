#!/usr/bin/env python3
from pathlib import Path
import re
import json
import logging
from typing import List, Dict
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from modular.shared.models import Session, Dependency
from modular.shared.base_logger import BaseLogger

class GradleHelper(BaseLogger):
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea'}
    DEPENDENCY_PATTERNS = [
        r"(?:implementation|api|compile|runtimeOnly|testImplementation)\s+['\"](.*?:.*?:.*?)['\"]",
        r"(?:implementation|api|compile|runtimeOnly|testImplementation)\(\s*group:\s*['\"](.*?)['\"],\s*name:\s*['\"](.*?)['\"],\s*version:\s*['\"](.*?)['\"]\)"
    ]

    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger if logger else self.get_logger("GradleHelper")
        self.logger.setLevel(logging.DEBUG)
        self.session_factory = Session

    def detect_java_build_tool(self, repo_dir):
        build_files = {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
        found_files = set()
        
        repo_path = Path(repo_dir).resolve()
        self.logger.debug(f"Scanning for build files in {repo_path}")

        for path in repo_path.rglob('*'):
            if any(part in self.EXCLUDE_DIRS for part in path.parts):
                continue
            if path.is_file() and path.name in build_files:
                found_files.add(path.name)
                self.logger.debug(f"Found build file: {path.relative_to(repo_path)}")

        maven = "pom.xml" in found_files
        gradle = bool(found_files - {"pom.xml"})
        
        if maven and gradle:
            self.logger.warning("Both Maven and Gradle files detected")
            return "Maven"
        elif maven:
            return "Maven"
        elif gradle:
            return "Gradle"
        return None

    def process_repo(self, repo_dir, repo, session=None):
        own_session = False
        if not session:
            session = self.session_factory()
            own_session = True
            self.logger.debug("Created new database session")

        try:
            repo_path = Path(repo_dir).resolve()
            self.logger.info(f"Processing repository: {repo_path.name}")

            if not repo_path.exists():
                raise ValueError(f"Invalid path: {repo_path}")
            if not repo_path.is_dir():
                raise ValueError(f"Not a directory: {repo_path}")

            dependencies = self._analyze_dependencies(repo_path)
            self._persist_dependencies(session, repo, dependencies)
            
            return {
                "repo_id": repo.repo_id,
                "dependency_count": len(dependencies),
                "status": "success"
            }
        except Exception as e:
            self.logger.error(f"Processing failed: {str(e)}", exc_info=True)
            session.rollback()
            return {
                "repo_id": repo.repo_id,
                "error": str(e),
                "status": "failed"
            }
        finally:
            if own_session and session:
                session.close()
                self.logger.debug("Closed database session")

    def _analyze_dependencies(self, repo_path: Path):
        self.logger.debug("Starting dependency analysis")
        build_files = self._find_gradle_files(repo_path)
        dependencies = []
        
        for build_file in build_files:
            try:
                content = build_file.read_text(encoding='utf-8')
                deps = self._extract_dependencies(content)
                dependencies.extend(deps)
                self.logger.debug(f"Found {len(deps)} dependencies in {build_file.name}")
            except Exception as e:
                self.logger.warning(f"Error reading {build_file}: {str(e)}")
        return dependencies

    def _find_gradle_files(self, root: Path):
        return [
            path for path in root.rglob('*')
            if path.is_file() 
            and path.name in {'build.gradle', 'build.gradle.kts'}
            and not any(part in self.EXCLUDE_DIRS for part in path.parts)
        ]

    def _extract_dependencies(self, content: str):
        dependencies = []
        for pattern in self.DEPENDENCY_PATTERNS:
            for match in re.finditer(pattern, content):
                try:
                    if match.groupdict():
                        dep = self._parse_map_style(match)
                    else:
                        dep = self._parse_string_style(match)
                    
                    dependencies.append({
                        'name': dep['name'],
                        'version': dep['version'],
                        'package_type': 'gradle',
                        'category': None,
                        'sub_category': None
                    })
                except Exception as e:
                    self.logger.warning(f"Skipping invalid dependency: {str(e)}")
        return dependencies

    def _persist_dependencies(self, session, repo, dependencies):
        if not dependencies:
            self.logger.info("No dependencies to persist")
            return

        try:
            stmt = insert(Dependency).values([{
                'repo_id': repo.repo_id,
                'name': dep['name'],
                'version': dep['version'],
                'package_type': dep['package_type'],
                'category': dep['category'],
                'sub_category': dep['sub_category']
            } for dep in dependencies]).on_conflict_do_update(
                constraint='uq_repo_name_version',
                set_={'package_type': insert(Dependency).excluded.package_type}
            )
            session.execute(stmt)
            session.commit()
            self.logger.info(f"Persisted {len(dependencies)} dependencies")
        except SQLAlchemyError as e:
            self.logger.error("Database error: {str(e)}")
            raise

    def _parse_map_style(self, match):
        return {
            'group': match.group(1),
            'name': match.group(2),
            'version': match.group(3),
            'scope': match.group(0).split('(')[0].strip()
        }

    def _parse_string_style(self, match):
        parts = match.group(1).split(':')
        if len(parts) < 3:
            raise ValueError(f"Invalid dependency: {match.group(1)}")
        return {
            'group': parts[0],
            'name': parts[1],
            'version': parts[2],
            'scope': match.group(0).split()[0]
        }

if __name__ == "__main__":
    repo_dir = "/tmp/gradle-project"
    repo_id = "example-org/sample-project"
    repo_slug = "sample-project"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    helper = GradleHelper()
    helper.logger.setLevel(logging.INFO)
    
    repo = MockRepo(repo_id, repo_slug)
    result = helper.process_repo(repo_dir, repo)
    
    print(json.dumps(result, indent=2))
    helper.logger.info("Analysis completed" if result['status'] == "success" else "Analysis failed")