import functools
import logging
import time
import inspect
from datetime import datetime
from shared.models import AnalysisExecutionLog
from shared.base_logger import BaseLogger

def analyze_execution(session_factory, stage=None):

    def decorator(func):
        # Validate function signature first
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        if len(params) < 3 or params[1].name != 'repo_dir' or params[2].name != 'repo':
            raise ValueError(f"Invalid method signature for {func.__name__}. "
                             "Expected: (self, repo_dir, repo, ...)")

        @functools.wraps(func)
        def wrapper(self, repo_dir, repo, *args, **kwargs):
            session = session_factory()
            method_name = func.__name__
            run_id = kwargs.get("run_id", "N/A")
            logger = getattr(self, 'logger', logging.getLogger('analysis'))

            try:
                # Validate parameters before processing
                if not isinstance(repo, dict):
                    raise TypeError(f"repo must be a dictionary, got {type(repo)}")
                if 'repo_id' not in repo:
                    raise KeyError("repo dictionary missing 'repo_id' key")

                repo_id = repo['repo_id']
                start_time = time.time()

                logger.info(f"Starting {stage} (Repo ID: {repo_id})...")

                # Call the original method
                result_message = func(self, repo_dir, repo, *args, **kwargs)
                elapsed_time = time.time() - start_time

                # Log success
                session.add(AnalysisExecutionLog(
                    method_name=method_name,
                    stage=stage,
                    run_id=run_id,
                    repo_id=repo_id,
                    status="SUCCESS",
                    message=result_message,
                    execution_time=datetime.utcnow(),
                    duration=elapsed_time
                ))
                session.commit()

                logger.info(
                    f"{stage} completed\n"
                    f"repo_id: {repo_id}\n"
                    f"duration: {elapsed_time:.2f}s"
                )

                return result_message

            except Exception as e:
                elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                error_message = str(e)
                repo_id = repo.get('repo_id', 'unknown') if isinstance(repo, dict) else 'invalid-repo'

                # Log failure
                if 'repo_id' in locals():
                    session.add(AnalysisExecutionLog(
                        method_name=method_name,
                        stage=stage,
                        run_id=run_id,
                        repo_id=repo_id,
                        status="FAILURE",
                        message=error_message,
                        execution_time=datetime.utcnow(),
                        duration=elapsed_time
                    ))
                    session.commit()

                logger.error(
                    f"{stage} failed\n"
                    f"repo_id: {repo_id}\n"
                    f"error: {error_message}"
                )
                raise RuntimeError(f"{stage} failed: {error_message}") from e

            finally:
                session.close()

        return wrapper
    return decorator
