from pathlib import Path

from core.observability.logging.manager import LoggingManager


def test_logger_cache(tmp_path: Path):

    manager = LoggingManager(tmp_path)

    a = manager.logger("workflow")

    b = manager.logger("workflow")

    assert a is b

def test_logger_creation(tmp_path: Path):

    manager = LoggingManager(tmp_path)

    logger = manager.logger("plugin.git")

    assert logger is not None

    # assert (tmp_path / "plugin" / "git.log").parent.exists()
    assert (tmp_path / "plugin.git.log").exists()
