import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from prefect import flow, task, get_run_logger

PGLOADER_PATH = "pgloader"
LOAD_FILE_DIR = "config/dbload"
MAX_PARALLEL_JOBS = 4

@task
def run_pgloader_job(load_file: Path):
    logger = get_run_logger()
    logger.info(f"Starting pgloader job: {load_file.name}")
    try:
        result = subprocess.run(
            [PGLOADER_PATH, str(load_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        logger.info(f"[{load_file.name}] Success:\n{result.stdout}")
        return (load_file.name, True)
    except subprocess.CalledProcessError as e:
        logger.error(f"[{load_file.name}] Failed:\n{e.stderr}")
        return (load_file.name, False)

@flow(name="Parallel pgloader jobs")
def run_all_pgloader_jobs(load_dir: str = LOAD_FILE_DIR):
    logger = get_run_logger()
    load_files = sorted(Path(load_dir).glob("*.load"))

    if not load_files:
        logger.warning("No .load files found in config/dbload/")
        return

    logger.info(f"Found {len(load_files)} .load files in {load_dir}.")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS) as executor:
        futures = {executor.submit(run_pgloader_job.fn, f): f.name for f in load_files}
        for future in as_completed(futures):
            file_name, status = future.result()
            results.append((file_name, status))

    success = [name for name, ok in results if ok]
    failed = [name for name, ok in results if not ok]

    logger.info(f"✓ Success: {success}")
    logger.warning(f"✗ Failed: {failed}")

if __name__ == "__main__":
    run_all_pgloader_jobs()