"""
Environment preparation.
"""

from pathlib import Path

from core.constants import (
    DATABASE_DIR,
    LOG_DIR,
    REPORT_DIR,
    RELEASE_DIR,
    RUNTIME_DIR,
    PID_DIR,
    STATE_DIR,
    LOCK_DIR,
)


class Environment:

    REQUIRED_DIRECTORIES = [
        DATABASE_DIR,
        LOG_DIR,
        REPORT_DIR,
        RELEASE_DIR,
        RUNTIME_DIR,
        PID_DIR,
        STATE_DIR,
        LOCK_DIR,
    ]

    @classmethod
    def prepare(cls):

        for directory in cls.REQUIRED_DIRECTORIES:
            Path(directory).mkdir(parents=True, exist_ok=True)