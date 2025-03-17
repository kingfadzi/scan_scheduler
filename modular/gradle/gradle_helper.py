#!/usr/bin/env python3
from pathlib import Path
import re
import json
import logging
from typing import List, Dict
from sqlalchemy.dialects.postgresql import insert
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
        self.logger.debug("Initialized GradleHelper instance")

    def process_repo(self, repo_dir, repo, session):
        self.logger.debug(f"Starting repository processing: {repo.repo_id}")
        try:
            repo_path = Path(repo_dir).resolve()
            self.logger.debug(f"Resolved repository path: {repo_path}")
            
            if not repo_path.exists():
                raise ValueError(f"Path does not exist: {repo_path}")
            if not repo_path.is_dir():
                raise ValueError(f"Not a directory: {repo_path}")

            dependencies = self._analyze_dependencies(repo_path)
            self.logger.debug(f"Found {len(dependencies)} raw dependencies")
            self._persist_dependencies(session, repo, dependencies)
            
            return {"repo_id": repo.repo_id, "dependency_count": len(dependencies), "status": "success"}
        except Exception as e:
            self.logger.error(f"Repository processing failed: {str(e)}", exc_info=True)
            session.rollback()
            return {"repo_id": repo.repo_id, "error": str(e), "status": "failed"}

    def _analyze_dependencies(self, repo_path: Path):
        self.logger.debug(f"Starting dependency analysis in {repo_path}")
        build_files = self._find_gradle_files(repo_path)
        self.logger.debug(f"Found {len(build_files)} build files to analyze")

        dependencies = []
        for idx, build_file in enumerate(build_files, 1):
            try:
                self.logger.debug(f"Processing file {idx}/{len(build_files)}: {build_file}")
                content = build_file.read_text(encoding='utf-8')
                file_deps = self._extract_dependencies(content)
                dependencies.extend(file_deps)
                self.logger.debug(f"Found {len(file_deps)} dependencies in {build_file.name}")
            except Exception as e:
                self.logger.warning(f"File processing error: {build_file} - {str(e)}")
        return dependencies

    def _find_gradle_files(self, root: Path):
        self.logger.debug(f"Searching for Gradle files in {root}")
        found_files = []
        for path in root.rglob('*'):
            if any(part in self.EXCLUDE_DIRS for part in path.parts):
                self.logger.debug(f"Skipping excluded path: {path}")
                continue
            if path.is_file() and path.name in {'build.gradle', 'build.gradle.kts'}:
                found_files.append(path)
                self.logger.debug(f"Found build file: {path}")
        self.logger.debug(f"Total build files found: {len(found_files)}")
        return found_files

    def _extract_dependencies(self, content: str):
        self.logger.debug("Extracting dependencies from content")
        dependencies = []
        for pattern_idx, pattern in enumerate(self.DEPENDENCY_PATTERNS, 1):
            self.logger.debug(f"Using pattern {pattern_idx}: {pattern}")
            matches = list(re.finditer(pattern, content))
            self.logger.debug(f"Found {len(matches)} matches with pattern {pattern_idx}")
            
            for match_idx, match in enumerate(matches, 1):
                try:
                    self.logger.debug(f"Processing match {match_idx}/{len(matches)}: {match.group(0)}")
                    dep = self._parse_map_style(match) if match.groupdict() else self._parse_string_style(match)
                    dependencies.append({
                        'name': dep['name'],
                        'version': dep['version'],
                        'package_type': 'gradle',
                        'category': None,
                        'sub_category': None
                    })
                    self.logger.debug(f"Parsed dependency: {dep['name']}:{dep['version']}")
                except Exception as e:
                    self.logger.warning(f"Failed parsing match {match_idx}: {str(e)}")
        return dependencies

    def _persist_dependencies(self, session, repo, dependencies):
        if not dependencies:
            self.logger.debug("Skipping persistence - no dependencies")
            return

        self.logger.debug(f"Preparing to persist {len(dependencies)} dependencies")
        values = [{
            'repo_id': repo.repo_id,
            'name': dep['name'],
            'version': dep['version'],
            'package_type': dep['package_type'],
            'category': dep['category'],
            'sub_category': dep['sub_category']
        } for dep in dependencies]

        self.logger.debug("Sample dependency values:")
        for dep in values[:3]:
            self.logger.debug(f"  {dep['name']}@{dep['version']}")

        stmt = insert(Dependency).values(values).on_conflict_do_update(
            constraint='uq_repo_name_version',
            set_={'package_type': insert(Dependency).excluded.package_type}
        )

        self.logger.debug("Executing database statement")
        session.execute(stmt)
        session.commit()
        self.logger.info(f"Persisted {len(dependencies)} dependencies")

    def _parse_map_style(self, match):
        self.logger.debug("Parsing map-style dependency")
        return {
            'group': match.group(1),
            'name': match.group(2),
            'version': match.group(3),
            'scope': match.group(0).split('(')[0].strip()
        }

    def _parse_string_style(self, match):
        self.logger.debug("Parsing string-style dependency")
        parts = match.group(1).split(':')
        if len(parts) < 3:
            raise ValueError(f"Invalid dependency format: {match.group(1)}")
        return {
            'group': parts[0],
            'name': parts[1],
            'version': parts[2],
            'scope': match.group(0).split()[0]
        }

if __name__ == "__main__":
    repo_dir = "/tmp/gradle-example"
    repo_id = "example-org/sample-project"
    repo_slug = "sample-project"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    session = Session()
    analyzer = GradleHelper()
    analyzer.logger.setLevel(logging.DEBUG)
    
    try:
        analyzer.logger.debug("Starting standalone execution")
        repo = MockRepo(repo_id, repo_slug)
        result = analyzer.process_repo(repo_dir, repo, session)
        analyzer.logger.debug(f"Raw result: {json.dumps(result, indent=2)}")
        
        if result['status'] == "success":
            analyzer.logger.info(f"Found {result['dependency_count']} dependencies")
        else:
            analyzer.logger.error(f"Failed with error: {result['error']}")
            
    except Exception as e:
        analyzer.logger.error(f"Fatal execution error: {str(e)}", exc_info=True)
    finally:
        session.close()
        analyzer.logger.debug("Database session closed")