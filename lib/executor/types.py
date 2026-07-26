from pathlib import Path
from typing import TypeAlias

PathLike: TypeAlias = Path
Command: TypeAlias = str | list[str]
Environment: TypeAlias = dict[str, str]