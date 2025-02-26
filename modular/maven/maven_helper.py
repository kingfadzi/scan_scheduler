import os
import logging
import subprocess
import xml.etree.ElementTree as ET
from config.config import Config
from modular.shared.base_logger import BaseLogger
from modular.shared.models import Dependency  # Assuming Dependency model is similar to other helpers

class MavenHelper(BaseLogger):
    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("MavenHelper")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    def process_repo(self, repo_dir, repo):

        self.logger.info(f"Processing repository at: {repo_dir}")
        if not os.path.isdir(repo_dir):
            self.logger.error(f"Invalid directory: {repo_dir}")
            return []

        effective_pom = self.generate_effective_pom(repo_dir)
        if not effective_pom or not os.path.isfile(effective_pom):
            return []

        return self.parse_dependencies(effective_pom, repo)

    def generate_effective_pom(self, repo_dir, output_file="effective-pom.xml"):

        self.logger.info(f"Checking for pom.xml in: {repo_dir}")
        pom_path = os.path.join(repo_dir, "pom.xml")

        if not os.path.isfile(pom_path):
            self.logger.warning(f"No pom.xml found at {pom_path}. Skipping effective POM generation.")
            return None

        self.logger.info(f"Found pom.xml at {pom_path}")
        command_list = ["mvn", "help:effective-pom", f"-Doutput={output_file}"]

        if Config.TRUSTSTORE_PATH:
            command_list.append(f"-Djavax.net.ssl.trustStore={Config.TRUSTSTORE_PATH}")
        if Config.TRUSTSTORE_PASSWORD:
            command_list.append(f"-Djavax.net.ssl.trustStorePassword={Config.TRUSTSTORE_PASSWORD}")

        self.logger.debug(f"Executing Maven command: {' '.join(command_list)}")

        try:
            result = subprocess.run(
                command_list,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True
            )
            self.logger.info("Maven help:effective-pom completed successfully.")
            return os.path.join(repo_dir, output_file)

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to generate effective-pom.xml: {e}")
            self.logger.debug(f"Stdout:\n{e.stdout}\nStderr:\n{e.stderr}")

            # Fallback to raw pom.xml if available
            if os.path.isfile(pom_path):
                self.logger.info("Falling back to raw pom.xml.")
                return pom_path
            self.logger.warning(f"Could not fallback to raw pom.xml because it is missing at {pom_path}.")
            return None

    def parse_dependencies(self, pom_file, repo):
        dependencies = []
        if not os.path.isfile(pom_file):
            return dependencies

        self.logger.info(f"Parsing dependencies from {pom_file}")
        try:
            tree = ET.parse(pom_file)
            root = tree.getroot()

            ns = {"m": "http://maven.apache.org/POM/4.0.0"}

            for dep in root.findall(".//m:dependency", ns):
                group_id = (
                    dep.find("m:groupId", ns).text
                    if dep.find("m:groupId", ns) is not None
                    else "unknown"
                )
                artifact_id = (
                    dep.find("m:artifactId", ns).text
                    if dep.find("m:artifactId", ns) is not None
                    else "unknown"
                )
                version = (
                    dep.find("m:version", ns).text
                    if dep.find("m:version", ns) is not None
                    else "unknown"
                )

                dependencies.append(
                    Dependency(
                        repo_id=repo.repo_id,
                        name=f"{group_id}:{artifact_id}",
                        version=version,
                        package_type="maven"
                    )
                )

            return dependencies

        except ET.ParseError as e:
            self.logger.error(f"Error parsing POM XML: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error parsing POM: {e}")

        return dependencies


# Define Repo class similar to PythonHelper
class Repo:
    def __init__(self, repo_id):
        self.repo_id = repo_id

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    repo_directory = "/tmp/sonar-metrics"
    repo = Repo(repo_id="maven_project")
    helper = MavenHelper()

    try:
        dependencies = helper.process_repo(repo_directory, repo)
        print(f"Dependencies found: {len(dependencies)}" if dependencies else "No dependencies found")

        #for dep in dependencies:
        #    print(f"Dependency found: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        print(f"An error occurred while processing the repository: {e}")
