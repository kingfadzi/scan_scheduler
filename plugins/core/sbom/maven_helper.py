import subprocess
import logging
from config.config import Config
from subprocess import CalledProcessError, TimeoutExpired

def prepare_maven_project(repo_dir: str):
    command = [
        "mvn", "-B", "-q",
        "help:effective-pom"
    ]

    if Config.TRUSTSTORE_PATH:
        command.append(f"-Djavax.net.ssl.trustStore={Config.TRUSTSTORE_PATH}")
    if Config.TRUSTSTORE_PASSWORD:
        command.append(f"-Djavax.net.ssl.trustStorePassword={Config.TRUSTSTORE_PASSWORD}")

    try:
        logging.info(f"Executing Maven command in directory: {repo_dir}")
        logging.debug(f"Running command: {' '.join(command)}")
        
        subprocess.run(
            command,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=Config.DEFAULT_PROCESS_TIMEOUT
        )
        
        logging.debug("Maven command executed successfully")
        
    except FileNotFoundError as e:
        logging.warning("Maven executable not found. Is Maven installed and in PATH?")
        
    except CalledProcessError as e:
        error_message = f"Maven command completed with error: {e.stderr.strip()}"
        logging.warning(error_message)
        
    except TimeoutExpired as e:
        logging.warning(f"Maven command timed out after {e.timeout} seconds")
