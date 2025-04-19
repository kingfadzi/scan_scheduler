import subprocess
from pathlib import Path
import asyncio
from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

PGLOADER_PATH = "pgloader"
LOAD_FILE_DIR = "config/dbload"

@task
async def run_pgloader_job(load_file: Path):
    logger = get_run_logger()
    logger.info(f"Starting pgloader job: {load_file.name}")

    process = await asyncio.create_subprocess_exec(
        PGLOADER_PATH,
        str(load_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        logger.info(f"[{load_file.name}] Success:\n{stdout.decode().strip()}")
        return (load_file.name, True)
    else:
        logger.error(f"[{load_file.name}] Failed:\n{stderr.decode().strip()}")
        return (load_file.name, False)

@flow(name="Parallel pgloader jobs", task_runner=ConcurrentTaskRunner())
async def run_all_pgloader_jobs(load_dir: str = LOAD_FILE_DIR):
    logger = get_run_logger()
    load_files = sorted(Path(load_dir).glob("*.load"))

    if not load_files:
        logger.warning("No .load files found in config/dbload/")
        return

    logger.info(f"Found {len(load_files)} .load files.")

    results = await asyncio.gather(*[
        run_pgloader_job.submit(f) for f in load_files
    ])

    success = [name for name, ok in results if ok]
    failed = [name for name, ok in results if not ok]

    logger.info(f"✓ Success: {success}")
    logger.warning(f"✗ Failed: {failed}")

if __name__ == "__main__":
    asyncio.run(run_all_pgloader_jobs())