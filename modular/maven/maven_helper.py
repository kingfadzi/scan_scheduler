import os
import logging
import subprocess

from modular.config import Config
from modular.base_logger import BaseLogger

class MavenHelper(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

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

        cmd_str = " ".join(command_list)
        self.logger.debug(f"Executing Maven command: {cmd_str}")

        try:
            result = subprocess.run(
                command_list,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True
            )
            self.logger.info("Maven help:effective-pom completed successfully.")
            if result.stdout:
                self.logger.debug(f"Command output:\n{result.stdout.strip()}")
            return os.path.join(repo_dir, output_file)

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to generate effective-pom.xml: {e}")
            self.logger.debug(f"Stdout:\n{e.stdout}\nStderr:\n{e.stderr}")

            if os.path.isfile(pom_path):
                self.logger.info("Falling back to raw pom.xml.")
                return pom_path
            self.logger.warning(f"Could not fallback to raw pom.xml because it is missing at {pom_path}.")
            return None

        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}")
            return None

        except PermissionError as e:
            self.logger.error(f"Permission error: {e}")
            return None

        except Exception as e:
            self.logger.error(f"Unexpected error running Maven: {e}")
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    helper = MavenHelper()
    project_dir = "/path/to/maven/project"
    result = helper.generate_effective_pom(project_dir)
    if result:
        print(f"Effective POM generated at: {result}")
    else:
        print("No effective POM generated.")
