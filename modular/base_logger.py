import logging

class BaseLogger:
    @classmethod
    def get_logger(cls, name=None):
        logger_name = name or cls.__name__
        logger = logging.getLogger(logger_name)

        if not logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.WARN)
            logger.propagate = False

        return logger
