# plugins/core/sbom/syft_helper.py

import subprocess
import os
from config.config import Config

def run_syft(repo_dir: str):
    """
    Runs Syft to generate an SBOM for the given repository directory.
    Outputs the SBOM as JSON to sbom.json.
    """
    sbom_path = os.path.join(repo_dir, "sbom.json")

    command = [
        "syft",
        repo_dir,
        "--output", "json",
        "--file", sbom_path
    ]

    subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=Config.DEFAULT_PROCESS_TIMEOUT
    )