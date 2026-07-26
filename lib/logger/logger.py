"""
Entropy Logger Manager
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LoggerManager:

    FORMAT = (
        "%(asctime)s | "
        "%(levelname)-8s | "
        "%(name)-15s | "
        "%(threadName)s | "
        "%(message)s"
    )

    def __init__(self):

        self.initialized = False

    def initialize(self, log_directory: Path):

        if self.initialized:
            return

        log_directory.mkdir(parents=True, exist_ok=True)

        log_file = log_directory / "entropy.log"

        formatter = logging.Formatter(self.FORMAT)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=20 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )

        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()

        console_handler.setFormatter(formatter)

        root = logging.getLogger()

        root.setLevel(logging.INFO)

        root.addHandler(file_handler)

        root.addHandler(console_handler)

        self.initialized = True

    def get_logger(self, name: str):

        return logging.getLogger(name)


logger_manager = LoggerManager()