import subprocess
import os
import json
from sqlalchemy.dialects.postgresql import insert

from plugins.core.gradle_sbom_generator import GradleSbomGenerator
from plugins.java.java_helper import is_gradle_project, has_gradle_lockfile, is_maven_project
from shared.models import Session, GrypeResult
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.base_logger import BaseLogger
import logging
from plugins.core.sbom_provider import SBOMProvider

class GrypeAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.sbom_provider = SBOMProvider(logger=self.logger, run_id=self.run_id) 

    @analyze_execution(session_factory=Session, stage="Grype Analysis")
    def run_analysis(self, repo_dir, repo, prepare_maven_project=None):
        self.logger.info(f"Starting Grype analysis for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")

        prep_step = None

        if is_gradle_project(repo_dir):
            if not has_gradle_lockfile(repo_dir):
                self.logger.info(f"Gradle project detected without lockfile for repo_id: {repo['repo_id']}. Using GradleSbomGenerator.")
                gradle_sbom_generator = GradleSbomGenerator(logger=self.logger, run_id=self.run_id)
                prep_step = lambda repo_dir: gradle_sbom_generator.run_analysis(repo_dir, repo)
        elif is_maven_project(repo_dir):
            self.logger.info(f"Maven project detected for repo_id: {repo['repo_id']}. Preparing effective-pom.")
            prep_step = prepare_maven_project


        sbom_file_path = self.sbom_provider.get_sbom_path(repo_dir=repo_dir, repo=repo, prep_step=prep_step)
        
        grype_file_path = os.path.join(repo_dir, "grype-results.json")

        # Check if the SBOM file exists
        if not os.path.exists(sbom_file_path):
            error_message = f"SBOM file not found for repository {repo['repo_name']} at path: {sbom_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Analyzing SBOM with Grype for repo_id: {repo['repo_id']} using SBOM at {sbom_file_path}.")

        try:
            env = os.environ.copy()
            env['GRYPE_DB_CACHE_DIR'] = Config.GRYPE_DB_CACHE_DIR
            self.logger.debug("Using GRYPE_DB_CACHE_DIR: %s", env['GRYPE_DB_CACHE_DIR'])
            command = [
                "grype",
                f"sbom:{sbom_file_path}",
                "--output", "json",
                "--file", grype_file_path
            ]
            self.logger.debug("Executing command: %s", " ".join(command))
            subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=300
            )
            self.logger.debug(f"Grype results written to: {grype_file_path}")
        except subprocess.TimeoutExpired as e:
            error_message = f"Grype command timed out for repo_id {repo['repo_id']} after {e.timeout} seconds."
            self.logger.error(error_message)
            raise RuntimeError(error_message)
        except subprocess.CalledProcessError as e:
            error_message = f"Grype command failed for repo_id {repo['repo_id']}: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(grype_file_path):
            error_message = f"Grype results file not found for repository {repo['repo_name']}. Expected at: {grype_file_path}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        self.logger.info(f"Reading Grype results from disk for repo_id: {repo['repo_id']}.")
        try:
            grype_result = self.parse_and_save_grype_results(grype_file_path, repo['repo_id'])
        except Exception as e:
            error_message = f"Error while parsing or saving Grype results for repository {repo['repo_name']}: {e}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        if isinstance(grype_result, str):
            return grype_result
        else:
            return json.dumps(grype_result)

    def parse_and_save_grype_results(self, grype_file_path, repo_id):
        self.logger.info(f"Reading Grype results from: {grype_file_path}")

        session = Session()
        try:
            with open(grype_file_path, "r") as file:
                grype_data = json.load(file)

            matches = grype_data.get("matches", [])
            if not matches:
                message = f"No vulnerabilities found for repo_id: {repo_id}"
                self.logger.info(message)
                return message

            session.query(GrypeResult).filter(GrypeResult.repo_id == repo_id).delete()

            for match in matches:
                vulnerability = match.get("vulnerability", {})
                artifact = match.get("artifact", {})
                locations = artifact.get("locations", [{}])

                cve = vulnerability.get("id", "No CVE")
                description = vulnerability.get("description", "No description provided")
                severity = vulnerability.get("severity", "UNKNOWN")

                metadata = artifact.get("metadata", {})
                pom_group_id = metadata.get("pomGroupID")
                pom_artifact_id = metadata.get("pomArtifactID")

                if pom_group_id and pom_artifact_id:
                    package = f"{pom_group_id}:{pom_artifact_id}"
                else:
                    package = artifact.get("name", "Unknown")

                version = artifact.get("version", "Unknown")
                file_path = locations[0].get("path", "N/A") if locations else "N/A"
                language = artifact.get("language", "Unknown")

                fix_data = vulnerability.get("fix", {})
                fix_versions_list = fix_data.get("versions", [])
                fix_versions = ", ".join(fix_versions_list)
                fix_state = fix_data.get("state", "not fixed")

                grype_result = GrypeResult(
                    repo_id=repo_id,
                    cve=cve,
                    description=description,
                    severity=severity,
                    package=package,
                    version=version,
                    file_path=file_path,
                    language=language,
                    fix_versions=fix_versions,
                    fix_state=fix_state,
                )

                session.add(grype_result)

            session.commit()

            self.logger.info(f"Saved {len(matches)} Grype vulnerabilities for repo_id: {repo_id}")
            return f"Found {len(matches)} vulnerabilities for repo_id: {repo_id}"

        except Exception as e:
            session.rollback()
            self.logger.error(f"Error parsing/saving Grype results for repo_id {repo_id}: {e}")
            raise

        finally:
            session.close()


    def save_grype_result(self, repo_id, cve, description, severity, package, version, file_path, language, fix_versions, fix_state):
        session = Session()
        try:

            session.add(
                GrypeResult(
                    repo_id=repo_id,
                    cve=cve,
                    description=description,
                    severity=severity,
                    package=package,
                    version=version,
                    file_path=file_path,
                    language=language,
                    fix_versions=fix_versions,
                    fix_state=fix_state,
                )
            )

            session.commit()
            self.logger.info(f"Grype result saved for repo_id: {repo_id}, cve: {cve}, package: {package}, version: {version}")
        except Exception as e:
            session.rollback()
            self.logger.exception(f"Error saving Grype result for repo_id {repo_id}, cve {cve}, package {package}, version {version}")
            raise
        finally:
            session.close()



import sys
import os
import json

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

    analyzer = GrypeAnalyzer(run_id="GRYPE_STANDALONE_001")
    session = Session()

    try:
        analyzer.logger.info(f"Starting standalone Grype analysis for repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)

        if isinstance(result, str):
            analyzer.logger.info(result)
        else:
            analyzer.logger.info(f"Grype analysis completed with {len(json.loads(result).get('matches', []))} findings")

    except Exception as e:
        analyzer.logger.error(f"Error during standalone Grype analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Database session closed for repo_id: {repo['repo_id']}")

