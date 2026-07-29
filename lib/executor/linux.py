"""
LinuxExecutor

Provides a thin abstraction over Linux operating system services.

Responsibilities
----------------
- Process execution
- Filesystem operations
- Archive handling
- Environment access
- File metadata

This class intentionally contains no deployment-specific logic.
Plugins decide what to execute; LinuxExecutor interacts with the OS.
"""

from __future__ import annotations

from .archive import ArchiveMixin
from .environment import EnvironmentMixin
from .filesystem import FileSystemMixin
from .information import InformationMixin
from .process import ProcessMixin


class LinuxExecutor(
    ProcessMixin,
    FileSystemMixin,
    ArchiveMixin,
    EnvironmentMixin,
    InformationMixin,
):
    """
    Linux operating system abstraction.

    This class exposes a unified API composed from specialized
    mixins. It intentionally contains no deployment-specific
    behavior.
    """

    pass
