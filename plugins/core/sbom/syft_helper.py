import subprocess
import os

def run_syft(repo_dir: str, output_path: str = None, logger=None):
    """
    Runs Syft against the given directory to generate an SBOM.
    """
    if not output_path:
        output_path = os.path.join(repo_dir, "sbom.json")

    if logger:
        logger.info(f"Running Syft for repo: {repo_dir}, output will be saved to {output_path}.")

    try:
        command = [
            "syft",
            repo_dir,
            "--output", "json",
            "--file", output_path
        ]
        if logger:
            logger.debug(f"Executing command: {' '.join(command)}")
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=300
        )
        if logger:
            logger.info(f"Syft SBOM generated successfully at {output_path}.")
    except subprocess.CalledProcessError as e:
        if logger:
            logger.error(f"Syft command failed: {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        if logger:
            logger.error(f"Syft scan timed out after 300s for {repo_dir}")
        raise