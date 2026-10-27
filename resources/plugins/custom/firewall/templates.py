"""
Record templates: a header row and the static records every file starts from.

Templates are CSV files (or .xlsx, first sheet). They come from two places:

- the plugin's own `templates/` folder (shipped with the plugin, edited in
  the plugin editor's spreadsheet view);
- templates saved by runs with `action: create_template`, kept in the
  plugin's data folder of the project (`templates/`), so they survive runs
  and plugin upgrades. A saved template with the same name wins over the
  shipped one.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .exceptions import XlGeneratorException
from .xlsx import read_first_sheet

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SUFFIXES = (".csv", ".xlsx")


@dataclass
class Template:
    name: str
    header: List[str]
    rows: List[List[str]] = field(default_factory=list)
    origin: str = "file"
    path: Optional[Path] = None

    def describe(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "origin": self.origin,
            "columns": list(self.header),
            "records": len(self.rows),
        }


def _clean(rows: List[List[str]]) -> List[List[str]]:
    """Strip cells, drop empty rows and trailing empty cells."""

    result = []
    for row in rows:
        values = [str(value).strip() for value in row]
        while values and values[-1] == "":
            values.pop()
        if values:
            result.append(values)
    return result


def parse_csv(text: str) -> List[List[str]]:
    """Rows of CSV text; the delimiter (comma, semicolon, tab, pipe) is detected."""

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def read_table(path: Path) -> List[List[str]]:
    """Rows of a .csv or .xlsx file."""

    if not path.is_file():
        raise XlGeneratorException(f"File '{path}' does not exist.")
    if path.suffix.lower() == ".xlsx":
        try:
            return _clean(read_first_sheet(path))
        except (ValueError, KeyError) as error:
            raise XlGeneratorException(f"Unable to read '{path}': {error}") from error
    if path.suffix.lower() == ".csv":
        return _clean(parse_csv(path.read_text(encoding="utf-8-sig")))
    raise XlGeneratorException(f"'{path.name}' must be a .csv or .xlsx file.")


def from_rows(
    name: str, rows: List[List[str]], origin: str, path: Optional[Path] = None
) -> Template:
    rows = _clean(rows)
    if not rows:
        raise XlGeneratorException(f"Template '{name}' has no header row.")
    header = rows[0]
    if any(not column for column in header):
        raise XlGeneratorException(
            f"Template '{name}' has an empty column name in its header: {header}."
        )
    seen = set()
    for column in header:
        if column.casefold() in seen:
            raise XlGeneratorException(f"Template '{name}' has the column '{column}' twice.")
        seen.add(column.casefold())
    records = [row + [""] * (len(header) - len(row)) for row in rows[1:]]
    too_long = [index for index, row in enumerate(records, start=1) if len(row) > len(header)]
    if too_long:
        raise XlGeneratorException(
            f"Template '{name}': record(s) {too_long} have more values than the header has columns."
        )
    return Template(name=name, header=header, rows=records, origin=origin, path=path)


def to_csv(header: List[str], rows: List[List[str]]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


class TemplateStore:
    def __init__(self, bundled: Path, saved: Path) -> None:
        self.bundled = bundled
        self.saved = saved

    @staticmethod
    def check_name(name: str) -> str:
        if not NAME.match(name or ""):
            raise XlGeneratorException(
                f"'{name}' is not a valid template name: use letters, digits, '_', '-' or '.' "
                "(up to 64 characters)."
            )
        return name

    def _files(self) -> Dict[str, Path]:
        """Template name -> file; saved templates replace shipped ones."""

        found: Dict[str, Path] = {}
        for folder in (self.bundled, self.saved):
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix.lower() in SUFFIXES and NAME.match(path.stem):
                    found[path.stem] = path
        return found

    def _origin(self, path: Path) -> str:
        return "saved" if path.parent == self.saved else "plugin"

    def names(self) -> List[str]:
        return sorted(self._files())

    def list(self) -> List[Template]:
        return [self.get(name) for name in self.names()]

    def get(self, name: str) -> Template:
        path = self._files().get(name)
        if path is None:
            available = ", ".join(self.names()) or "none"
            raise XlGeneratorException(f"No template '{name}'. Available templates: {available}.")
        return from_rows(name, read_table(path), self._origin(path), path)

    def save(
        self, name: str, header: List[str], rows: List[List[str]], overwrite: bool
    ) -> Template:
        self.check_name(name)
        template = from_rows(name, [header] + rows, "saved")
        path = self.saved / f"{name}.csv"
        if path.exists() and not overwrite:
            raise XlGeneratorException(
                f"A saved template '{name}' already exists. Set 'overwrite' to replace it."
            )
        self.saved.mkdir(parents=True, exist_ok=True)
        stale = self.saved / f"{name}.xlsx"
        if stale.exists():
            stale.unlink()
        path.write_text(to_csv(template.header, template.rows), encoding="utf-8")
        template.path = path
        return template

    def delete(self, name: str) -> Path:
        self.check_name(name)
        for suffix in SUFFIXES:
            path = self.saved / f"{name}{suffix}"
            if path.exists():
                path.unlink()
                return path
        raise XlGeneratorException(
            f"No saved template '{name}' "
            "(templates shipped with the plugin are edited in the plugin editor)."
        )
