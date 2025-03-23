import functools
import inspect
import logging
import time
from datetime import datetime
from shared.models import AnalysisExecutionLog

def analyze_execution(session_factory, stage=None):

    def decorator(func):
        sig = inspect.signature(func)
        params = sig.parameters

        # Validate required parameters exist
        if 'repo' not in params:
            raise ValueError(f"Method {func.__name__} must have a 'repo' parameter")

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Validate run_id is set on the analyzer instance
            if not hasattr(self, 'run_id') or not self.run_id:
                raise RuntimeError("Analyzer instance missing 'run_id'. ")

            session = session_factory()
            method_name = func.__name__
            logger = getattr(self, 'logger', logging.getLogger('analysis'))

            try:
                # Bind and validate arguments
                bound_args = sig.bind(self, *args, **kwargs)
                bound_args.apply_defaults()
                parameters = bound_args.arguments

                # Extract and validate repo information
                repo = parameters['repo']
                repo_dir = parameters.get('repo_dir', None)

                if not isinstance(repo, dict):
                    raise TypeError(f"repo must be dict, got {type(repo)}")
                if 'repo_id' not in repo:
                    raise KeyError("repo missing 'repo_id'")

                repo_id = repo['repo_id']
                start_time = time.time()
                logger.debug(f"Starting {stage} (Repo ID: {repo_id}, Run ID: {self.run_id})")

                # Execute decorated method
                result = func(self, *args, **kwargs)
                elapsed_time = time.time() - start_time

                # Persist success log
                session.add(AnalysisExecutionLog(
                    method_name=method_name,
                    stage=stage,
                    run_id=self.run_id,
                    repo_id=repo_id,
                    status="SUCCESS",
                    message=str(result),
                    execution_time=datetime.utcnow(),
                    duration=elapsed_time
                ))
                session.commit()

                logger.info(f"{stage} completed for {repo_id} (Run: {self.run_id}, Duration: {elapsed_time:.2f}s)")
                return result

            except Exception as e:
                elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                error_message = str(e)
                repo_id = repo.get('repo_id', 'unknown') if isinstance(repo, dict) else 'invalid-repo'

                # Persist failure log
                session.add(AnalysisExecutionLog(
                    method_name=method_name,
                    stage=stage,
                    run_id=self.run_id,
                    repo_id=repo_id,
                    status="FAILURE",
                    message=error_message,
                    execution_time=datetime.utcnow(),
                    duration=elapsed_time
                ))
                session.commit()

                logger.error(f"{stage} failed for {repo_id} (Run: {self.run_id}): {error_message}")
                raise RuntimeError(f"{stage} failed: {error_message}") from e

            finally:
                session.close()

        return wrapper
    return decorator
