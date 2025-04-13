import subprocess
import logging
from config.config import Config
from subprocess import CalledProcessError, TimeoutExpired
import os

def prepare_maven_project(repo_dir: str, logger=None):
    """
    Runs 'mvn help:effective-pom' in the given directory to prepare the Maven project.
    Supports optional injected logger; falls back to default logging if none.
    """
    if not os.path.exists(repo_dir):
        msg = f"Directory does not exist: {repo_dir}"
        if logger:
            logger.error(msg)
        else:
            logging.error(msg)
        raise FileNotFoundError(msg)

    command = [
        "mvn", "-B", "-q", "help:effective-pom"
    ]

    if Config.TRUSTSTORE_PATH:
        command.append(f"-Djavax.net.ssl.trustStore={Config.TRUSTSTORE_PATH}")
    if Config.TRUSTSTORE_PASSWORD:
        command.append(f"-Djavax.net.ssl.trustStorePassword={Config.TRUSTSTORE_PASSWORD}")

    try:
        log_info(logger, f"Executing Maven effective-pom command in {repo_dir}")
        log_debug(logger, f"Running command: {' '.join(command)}")

        subprocess.run(
            command,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=Config.DEFAULT_PROCESS_TIMEOUT
        )

        log_info(logger, "Maven effective-pom generation completed successfully.")

    except FileNotFoundError:
        log_warning(logger, "Maven executable not found. Is Maven installed and in PATH?")
    except CalledProcessError as e:
        log_warning(logger, f"Maven command failed: {e.stderr.strip()}")
    except TimeoutExpired as e:
        log_warning(logger, f"Maven command timed out after {e.timeout} seconds.")

# --- Small helpers to fallback logging ---
def log_info(logger, message):
    if logger:
        logger.info(message)
    else:
        logging.info(message)

def log_debug(logger, message):
    if logger:
        logger.debug(message)
    else:
        logging.debug(message)

def log_warning(logger, message):
    if logger:
        logger.warning(message)
    else:
        logging.warning(message)