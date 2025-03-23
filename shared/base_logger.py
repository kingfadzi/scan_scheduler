import logging

class BaseLogger:
    @classmethod
    def get_logger(cls, name=None):
        logger = logging.getLogger(name or cls.__name__)

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(levelname)s - %(name)s: %(message)s'
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.WARNING)
            logger.propagate = False

        return logger
