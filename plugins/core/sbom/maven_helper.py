# plugins/core/sbom/maven_helper.py

import subprocess
from config.config import Config

def prepare_maven_project(repo_dir: str):
    """
    Prepares a Maven project by generating its effective-pom.
    This ensures Syft can detect transitive dependencies.
    """
    command = ["mvn", "help:effective-pom"]

    subprocess.run(
        command,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
        timeout=Config.DEFAULT_PROCESS_TIMEOUT
    )