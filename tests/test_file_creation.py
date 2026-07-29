from pathlib import Path

from lib.executor.filesystem import FileSystemMixin


class TestFileSystem:

    def test_exists(self, tmp_path: Path):

        file = tmp_path / "hello.txt"

        file.write_text("hello")

        fs = FileSystemMixin()

        assert fs.exists(file)
