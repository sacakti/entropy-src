from pathlib import Path

import pytest

from core.context import EntropyContext


@pytest.fixture
def context() -> EntropyContext:
    return EntropyContext()
