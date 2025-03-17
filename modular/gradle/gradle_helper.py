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
        if logger is None:
            self.logger = self.get_logger("GradleHelper")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    def process_repo(self, repo_dir, repo, session):
        """Main processing method with database session"""
        self.logger.info(f"Processing repository: {repo.repo_name}")
        
        try:
            repo_path = Path(repo_dir).resolve()
            if not repo_path.exists() or not repo_path.is_dir():
                raise ValueError(f"Invalid repository path: {repo_path}")

            dependencies = self._analyze_dependencies(repo_path)
            self._persist_dependencies(session, repo, dependencies)
            
            return {
                "repo_id": repo.repo_id,
                "dependency_count": len(dependencies),
                "status": "success"
            }
        except Exception as e:
            self.logger.error(f"Processing failed: {str(e)}")
            session.rollback()
            return {
                "repo_id": repo.repo_id,
                "error": str(e),
                "status": "failed"
            }

    def _analyze_dependencies(self, repo_path: Path) -> List[Dict]:
        """Analyze and extract dependencies from Gradle files"""
        dependencies = []
        build_files = self._find_gradle_files(repo_path)
        
        for build_file in build_files:
            try:
                content = build_file.read_text(encoding='utf-8')
                dependencies.extend(self._extract_dependencies(content))
            except Exception as e:
                self.logger.warning(f"Error processing {build_file.name}: {str(e)}")
        
        return dependencies

    def _find_gradle_files(self, root: Path) -> List[Path]:
        """Locate Gradle build files"""
        return [
            path for path in root.rglob('*')
            if path.is_file() 
            and path.name in {'build.gradle', 'build.gradle.kts'}
            and not any(part in self.EXCLUDE_DIRS for part in path.parts)
        ]

    def _extract_dependencies(self, content: str) -> List[Dict]:
        """Parse dependencies from build file content"""
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

    def _persist_dependencies(self, session, repo, dependencies: List[Dict]):
        """Store dependencies in database with conflict handling"""
        if not dependencies:
            self.logger.info("No dependencies to persist")
            return

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
        self.logger.info(f"Persisted {len(dependencies)} Gradle dependencies")

    def _parse_map_style(self, match) -> Dict:
        """Parse map-style dependency declaration"""
        return {
            'group': match.group('group'),
            'name': match.group('name'),
            'version': match.group('version'),
            'scope': match.group(0).split('(')[0].strip()
        }

    def _parse_string_style(self, match) -> Dict:
        """Parse string-style dependency declaration"""
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
    # Standalone execution configuration
    repo_dir = "/tmp/gradle-project"
    repo_id = "example-org/sample-project"
    repo_slug = "sample-project"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    # Initialize components
    repo = MockRepo(repo_id, repo_slug)
    session = Session()
    analyzer = GradleHelper()
    analyzer.logger.setLevel(logging.INFO)

    try:
        result = analyzer.process_repo(repo_dir, repo, session)
        print(json.dumps(result, indent=2))
        
        if result['status'] == "success":
            analyzer.logger.info(f"Analysis succeeded: {result['dependency_count']} dependencies found")
        else:
            analyzer.logger.error(f"Analysis failed: {result['error']}")
            
    except Exception as e:
        analyzer.logger.error(f"Fatal error: {str(e)}")
    finally:
        session.close()
        analyzer.logger.info("Database session closed")