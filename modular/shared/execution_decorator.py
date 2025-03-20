import functools
import logging
import time
from datetime import datetime
from modular.shared.models import AnalysisExecutionLog
from modular.shared.base_logger import BaseLogger

class AnalysisLogger(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("AnalyzeExecution")
        self.logger.setLevel(logging.DEBUG)

def analyze_execution(session_factory, stage=None):

    decorator_logger = AnalysisLogger().logger

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            session = session_factory()
            method_name = func.__name__
            run_id = kwargs.get("run_id", "N/A")

            self_instance = args[0] if len(args) > 0 and hasattr(args[0], "__class__") else None

            # Determine the repository from kwargs or positional arguments.
            repo = kwargs.get("repo") or (args[1] if self_instance and len(args) > 1 else args[0])

            if not repo:
                session.close()
                raise ValueError(
                    f"Decorator for stage '{stage}' expected 'repo' but got None. "
                    "Ensure you pass 'repo' either as the first positional argument or as a kwarg."
                )

            # Check that repo is a dict with a 'repo_id' key.
            if not isinstance(repo, dict) or "repo_id" not in repo:
                session.close()
                raise ValueError(f"Expected key 'repo_id' missing in repo object: {repo}")

            repo_id = repo["repo_id"]
            start_time = time.time()

            try:
                decorator_logger.info(
                    f"Starting {stage} (Repo ID: {repo_id})..."
                )

                result_message = func(*args, **kwargs)
                elapsed_time = time.time() - start_time

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

                decorator_logger.info(
                    f"\n{stage} completed successfully:\n"
                    f"  repo_id={repo_id}\n"
                    f"  duration={elapsed_time:.2f}s"
                )

                return result_message

            except Exception as e:
                elapsed_time = time.time() - start_time
                error_message = str(e)

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

                decorator_logger.error(
                    f"\n{stage} failed:\n"
                    f"  repo_id={repo_id}\n"
                    f"  duration={elapsed_time:.2f}s\n"
                    f"  error_message='{error_message}'"
                )
                raise RuntimeError(error_message)

            finally:
                session.close()

        return wrapper
    return decorator
