import subprocess
import os
import json
import logging
from sqlalchemy.dialects.postgresql import insert

from plugins.core.syft_analysis import SyftAnalyzer
from shared.models import Session
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.base_logger import BaseLogger

from plugins.core.syft_dependency_model import SyftDependency  # updated model import

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
        self.logger.info(f"Reading SBOM from: {sbom_file_path}")
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
            processed_count = 0

            for artifact in artifacts:
                package_name = artifact.get("name", "Unknown")
                version = artifact.get("version", "Unknown")
                package_type = artifact.get("type", "Unknown")
                licenses = ", ".join([l.get("value", "Unknown") for l in artifact.get("licenses", [])])
                locations = ", ".join([loc.get("path", "Unknown") for loc in artifact.get("locations", [])])
                language = artifact.get("language", "Unknown")
                
                session.execute(
                    insert(SyftDependency).values(
                        id=f"{repo_id}-{package_name}-{version}",  # still populate ID nicely
                        repo_id=repo_id,
                        package_name=package_name,
                        version=version,
                        package_type=package_type,
                        licenses=licenses,
                        locations=locations,
                        language=language
                    ).on_conflict_do_update(
                        index_elements=['repo_id', 'package_name', 'version'],  # true uniqueness!
                        set_={
                            'package_type': package_type,
                            'licenses': licenses,
                            'locations': locations,
                            'language': language
                        }
                    )
                )
                processed_count += 1

            session.commit()
            self.logger.debug(f"Successfully processed {processed_count} dependencies for repo_id: {repo_id}")
            return processed_count

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in SBOM file: {e}")
            raise
        except Exception as e:
            self.logger.exception(f"Error processing dependencies for repo_id {repo_id}: {e}")
            raise
        finally:
            if session:
                session.close()

if __name__ == "__main__":
    repo_slug = "wrongsecrets"
    repo_id = "sonar-metrics"
    
    repo = {
        'repo_id': repo_id,
        'repo_slug': repo_slug,
        'repo_name': repo_slug
    }
    
    analyzer = SyftDependencyAnalyzer(run_id="SYFT_DEP_001")
    repo_dir = f"/tmp/{repo['repo_slug']}"
    
    try:
        analyzer.logger.info(f"Starting dependency analysis for repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Analysis completed. Result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during dependency analysis: {e}")