import logging

def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """Menyiapkan logger dengan file output."""
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger
