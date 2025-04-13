import sys
import os
import yaml
import re
import logging
from pprint import pprint
from datetime import datetime

from config.config import Config
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.models import Session, IacComponent  # IacComponent must be defined in shared.models

class IaCScanner(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    def load_rules(self):
        rules = []
        rules_dir = Config.IAC_RULES_PATH

        if not os.path.isdir(rules_dir):
            self.logger.error(f"IaC rules path '{rules_dir}' does not exist or is not a directory.")
            return rules

        for filename in os.listdir(rules_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                filepath = os.path.join(rules_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = yaml.safe_load(f)
                        if data and "categories" in data:
                            rules.extend(data["categories"])
                            self.logger.info(f"Loaded {len(data['categories'])} categories from {filename}")
                        else:
                            self.logger.warning(f"File {filename} missing 'categories' key. Skipping.")
                except Exception as e:
                    self.logger.error(f"Failed to load rules from {filename}: {e}")

        self.logger.info(f"Total loaded IaC categories: {len(rules)}")
        return rules

    def find_all_files(self, root_path):
        for dirpath, _, filenames in os.walk(root_path):
            for filename in filenames:
                yield os.path.join(dirpath, filename)

    def file_matches_framework(self, file_path, framework):
        filename = os.path.basename(file_path)
        for pattern in framework.get("file_patterns", []):
            if re.search(pattern, filename):
                return True
        return False

    def content_matches_framework(self, file_path, framework):
        if not framework.get("content_patterns"):
            return True  # No content patterns needed
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return False  # Unreadable file
        for pattern in framework["content_patterns"]:
            if re.search(pattern, content, flags=re.MULTILINE | re.IGNORECASE):
                return True
        return False

    def detect_frameworks_in_file(self, file_path, rules):
        detections = []
        for category in rules:
            for subcategory in category.get("subcategories", []):
                for framework in subcategory.get("frameworks", []):
                    if self.file_matches_framework(file_path, framework):
                        if self.content_matches_framework(file_path, framework):
                            detections.append({
                                "category": category["name"],
                                "subcategory": subcategory["name"],
                                "framework": framework["name"]
                            })
        return detections

    def scan_repository(self, repo_path, rules):
        all_detections = []
        for file_path in self.find_all_files(repo_path):
            matches = self.detect_frameworks_in_file(file_path, rules)
            if matches:
                all_detections.append({
                    "file": file_path,
                    "matches": matches
                })
        return all_detections

    def store_detections(self, detections, repo, session):
        """
        Delete all existing rows for the given repo_id, insert all new detections,
        and commit the transaction. Rollback on exception.
        """
        try:
            # Delete existing records for repo_id
            deleted = session.query(IacComponent).filter(IacComponent.repo_id == repo.get("repo_id")).delete()
            self.logger.info(f"Deleted {deleted} existing records for repo_id: {repo.get('repo_id')}")
            
            # Insert new detection records
            for item in detections:
                file_path = item.get("file")
                for match in item.get("matches", []):
                    component = IacComponent(
                        repo_id=repo.get("repo_id"),
                        repo_slug=repo.get("repo_slug"),
                        repo_name=repo.get("repo_name"),
                        file_path=file_path,
                        category=match.get("category"),
                        subcategory=match.get("subcategory"),
                        framework=match.get("framework"),
                        scan_timestamp=datetime.utcnow()
                    )
                    session.add(component)
            session.commit()
            self.logger.info(f"Stored {len(detections)} detection records to the database for repo {repo.get('repo_id')}.")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error storing detections for repo {repo.get('repo_id')}: {e}")

    @analyze_execution(session_factory=Session, stage="IaC Scan")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting IaC scan for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")
        rules = self.load_rules()
        detections = self.scan_repository(repo_dir, rules)

        if not detections:
            self.logger.info("No IaC or platform components detected.")
            return []

        self.logger.info(f"Detected IaC/platform components in {len(detections)} files.")
        return detections

# --- Main entrypoint (standalone runner) ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python iac_scanner.py /path/to/repo_dir")
        sys.exit(1)

    repo_dir = sys.argv[1]
    repo_name = os.path.basename(os.path.normpath(repo_dir))
    repo_slug = repo_name
    repo_id = f"standalone_test/{repo_slug}"

    repo = {
        "repo_id": repo_id,
        "repo_slug": repo_slug,
        "repo_name": repo_name
    }

    analyzer = IaCScanner(run_id="IAC_STANDALONE_001")
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone IaC scan for repo_id: {repo['repo_id']}")
        detections = analyzer.run_analysis(repo_dir, repo=repo)

        # Print the detections as a list for easy inspection
        from pprint import pprint
        pprint(detections)

        # Store detections in the database (delete old ones first)
        if detections:
            analyzer.store_detections(detections, repo, session)
    except Exception as e:
        analyzer.logger.error(f"Error during standalone IaC scan: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}")