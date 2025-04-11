import hashlib
import subprocess
import os
import json
import logging
import uuid

from sqlalchemy.dialects.postgresql import insert

from plugins.core.syft_analysis import SyftAnalyzer
from shared.models import Session, SyftDependency
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.base_logger import BaseLogger


class SyftDependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Dependency Analysis")
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Starting dependency analysis for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")

        syft_analyzer = SyftAnalyzer(
            logger=self.logger,
            run_id=self.run_id
        )

        syft_analyzer.generate_sbom(repo_dir=repo_dir, repo=repo)

        sbom_file_path = os.path.join(repo_dir, "sbom.json")

        if not os.path.exists(sbom_file_path):
            error_message = f"SBOM file not found for repository {repo['repo_name']} at path: {sbom_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Processing SBOM for dependencies for repo_id: {repo['repo_id']} using SBOM at {sbom_file_path}.")

        try:
            result = self.parse_and_save_dependencies(sbom_file_path, repo['repo_id'])
            return json.dumps({"status": "success", "dependencies_processed": result})
        except Exception as e:
            error_message = f"Error processing dependencies for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)


    def parse_and_save_dependencies(self, sbom_file_path, repo_id):
        session = None
        try:
            with open(sbom_file_path, "r") as file:
                sbom_data = json.load(file)

            artifacts = sbom_data.get("artifacts", [])
            if not artifacts:
                message = f"No dependencies found for repo_id: {repo_id}"
                self.logger.info(message)
                return message

            session = Session()
            session.query(SyftDependency).filter(
                SyftDependency.repo_id == repo_id
            ).delete()

            processed_count = 0
            seen = set()

            for artifact in artifacts:
                metadata = artifact.get("metadata", {})
                pom_properties = metadata.get("pomProperties", {})
                group_id = pom_properties.get("groupId")
                artifact_id = pom_properties.get("artifactId")

                if group_id and artifact_id:
                    package_name = f"{group_id}:{artifact_id}"
                else:
                    package_name = artifact.get("name", "Unknown")

                version = artifact.get("version", "Unknown")
                key = (package_name, version)

                if key in seen:
                    continue
                seen.add(key)

                package_type = artifact.get("type", "Unknown")
                licenses = ", ".join([l.get("value", "Unknown") for l in artifact.get("licenses", [])])
                locations = ", ".join([loc.get("path", "Unknown") for loc in artifact.get("locations", [])])
                language = artifact.get("language", "Unknown")

                dependency = SyftDependency(
                    id=str(uuid.uuid4()),
                    repo_id=repo_id,
                    package_name=package_name,
                    version=version,
                    package_type=package_type,
                    licenses=licenses,
                    locations=locations,
                    language=language
                )
                session.add(dependency)
                processed_count += 1

            session.commit()
            self.logger.debug(f"Successfully processed {processed_count} dependencies for repo_id: {repo_id}")
            return processed_count

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in SBOM file: {e}")
            raise
        except Exception as e:
            if session:
                session.rollback()
            self.logger.exception(f"Error processing dependencies for repo_id {repo_id}: {e}")
            raise
        finally:
            if session:
                session.close()


import sys
import os

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py /path/to/repo_dir")
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

    analyzer = SyftDependencyAnalyzer(run_id="SYFT_DEP_001")

    try:
        analyzer.logger.info(f"Starting dependency analysis for repo_dir: {repo_dir}, repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Analysis completed. Result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during dependency analysis: {e}")
