from dataclasses import dataclass
from typing import Optional

from config.config_loader import Configuration
from lib.output.output import OutputManager


@dataclass
class ReleaseContext:

    release_id: Optional[str] = None

    target: Optional[str] = None

    workflow: Optional[str] = None

    step: int = 0

    plugin: Optional[str] = None


class EntropyContext:

    def __init__(self):

        self.config: Optional[Configuration] = None

        self.output: Optional[OutputManager] = None

        self.database = None

        self.release = ReleaseContext()