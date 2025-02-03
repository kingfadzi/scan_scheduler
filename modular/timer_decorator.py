import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.info(f"Starting function {func.__name__}...")
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        logger.info(f"Function {func.__name__} completed in {elapsed_time:.2f} seconds.")
        return result
    return wrapper
