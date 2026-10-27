"""
Excel file generation from record templates.

A template holds a header and static records (for example ten firewall
rules with their destinations, ports and protocols). The plugin fills the
source columns of every record with the source(s) the user gives and writes
an .xlsx file:

- mode `single`: one source (name, ip, optional region) on all records;
- mode `multiple`: each source gets its own copy of the records, stacked on
  one sheet or one sheet per source.

Templates can also be created, listed and deleted (`action`).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import XlGeneratorException
from .templates import Template, TemplateStore, from_rows, parse_csv, read_table
from .xlsx import write_workbook

ACTIONS = ("generate", "create_template", "list_templates", "delete_template")
MODES = ("single", "multiple")
LAYOUTS = ("rows", "sheets")
DEFAULT_TEMPLATE = "firewall"
SAFE_FILE = re.compile(r"[^A-Za-z0-9_.-]+")
RANGE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")


@dataclass
class Source:
    name: str
    ip: str
    region: str = ""


def _key(text: str) -> str:
    """'Source  IP' -> 'source ip'."""

    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def source_columns(header: List[str]) -> Dict[str, Optional[int]]:
    """
    Where the source name, ip and region go: the first columns whose names
    start with 'source' and mention 'name', 'ip' and 'region'.
    """

    found: Dict[str, Optional[int]] = {"name": None, "ip": None, "region": None}
    for index, column in enumerate(header):
        words = _key(column).split()
        if not words or words[0] not in ("source", "src"):
            continue
        for field, markers in (
            ("name", ("name", "host")),
            ("ip", ("ip", "address")),
            ("region", ("region",)),
        ):
            if found[field] is None and any(marker in words[1:] for marker in markers):
                found[field] = index
                break
    return found


class XlGeneratorPlugin(
    BasePlugin,
):
    """
    Generate Excel files from record templates.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Run the selected action.
        """

        action = (self.arguments.string("action") or "generate").lower()
        if action not in ACTIONS:
            raise XlGeneratorException(
                f"Unknown action '{action}'. Use one of: {', '.join(ACTIONS)}."
            )

        store = TemplateStore(
            Path(__file__).resolve().parent / "templates",
            Path(self.data_directory) / "templates",
        )

        with self.activity(
            "xl_generator",
        ):
            if action == "generate":
                self._generate(store)
            elif action == "create_template":
                self._create_template(store)
            elif action == "list_templates":
                self._list_templates(store)
            else:
                self._delete_template(store)

        return PluginResult(
            success=True,
            changed=action != "list_templates",
            outputs=dict(
                self.outputs,
            ),
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def _template(self, store: TemplateStore) -> Template:
        template_file = self.arguments.path("template_file")
        if template_file:
            path = Path(template_file).expanduser()
            return from_rows(path.stem, read_table(path), "file", path)
        return store.get(self.arguments.string("template") or DEFAULT_TEMPLATE)

    def _list_templates(self, store: TemplateStore) -> None:
        templates = [template.describe() for template in store.list()]
        for item in templates:
            self.message.info(
                f"{item['name']} ({item['origin']}): {item['records']} record(s); "
                f"columns: {', '.join(item['columns'])}"
            )
        if not templates:
            self.message.warning("No templates yet.")
        self.outputs["templates"] = templates

    def _delete_template(self, store: TemplateStore) -> None:
        name = self.arguments.string("template_name", required=True)
        path = store.delete(name)
        self.message.success(f"Saved template '{name}' deleted ({path}).")
        self.outputs["template"] = name

    def _create_template(self, store: TemplateStore) -> None:
        name = store.check_name(self.arguments.string("template_name", required=True))
        columns = self.arguments.list("columns")
        rows = self.arguments.get("rows")

        if columns:
            header = [str(column).strip() for column in columns]
            base_rows: List[List[str]] = []
            origin = "the given columns"
        else:
            base = self._template(store)
            header, base_rows = base.header, base.rows
            origin = f"template '{base.name}'"

        records = self._template_rows(rows, header) if rows not in (None, "", []) else base_rows
        template = store.save(
            name, header, records, bool(self.arguments.boolean("overwrite", False))
        )

        self.message.success(
            f"Template '{name}' saved from {origin}: {len(template.header)} column(s), "
            f"{len(template.rows)} record(s) ({template.path})."
        )
        self.outputs["template"] = name
        self.outputs["file"] = str(template.path)
        self.outputs["rows"] = len(template.rows)

    @staticmethod
    def _template_rows(rows: Any, header: List[str]) -> List[List[str]]:
        """Records for a new template: lists, objects by column name, or CSV text."""

        if isinstance(rows, str):
            return [
                [cell.strip() for cell in row]
                for row in parse_csv(rows)
                if any(cell.strip() for cell in row)
            ]
        if not isinstance(rows, list):
            raise XlGeneratorException("'rows' must be a list of records or CSV text.")

        columns = {_key(column): index for index, column in enumerate(header)}
        result = []
        for number, row in enumerate(rows, start=1):
            if isinstance(row, dict):
                values = [""] * len(header)
                for column, value in row.items():
                    if _key(str(column)) not in columns:
                        raise XlGeneratorException(
                            f"Record {number} has the column '{column}', "
                            "which the template does not have."
                        )
                    values[columns[_key(str(column))]] = "" if value is None else str(value)
                result.append(values)
            elif isinstance(row, list):
                result.append(["" if value is None else str(value) for value in row])
            elif isinstance(row, str):
                result.extend([cell.strip() for cell in line] for line in parse_csv(row))
            else:
                raise XlGeneratorException(
                    f"Record {number} must be a list, an object or a CSV line."
                )
        return result

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def _generate(self, store: TemplateStore) -> None:
        template = self._template(store)
        mode = (self.arguments.string("mode") or "single").lower()
        if mode not in MODES:
            raise XlGeneratorException(f"Unknown mode '{mode}'. Use 'single' or 'multiple'.")
        layout = (self.arguments.string("layout") or "rows").lower()
        if layout not in LAYOUTS:
            raise XlGeneratorException(f"Unknown layout '{layout}'. Use 'rows' or 'sheets'.")

        records = self._select_records(template)
        values = self._values(template)
        sources = self._single_source() if mode == "single" else self._multiple_sources()
        columns = source_columns(template.header)

        missing = [
            label
            for field, label in (("name", "source name"), ("ip", "source ip"))
            if columns[field] is None
        ]
        if missing:
            raise XlGeneratorException(
                f"Template '{template.name}' has no {' or '.join(missing)} column "
                f"(columns: {', '.join(template.header)}). "
                "Name them like 'Source name' and 'Source ip'."
            )
        if columns["region"] is None and any(source.region for source in sources):
            self.message.warning(
                f"Template '{template.name}' has no source region column; "
                "the region is not written."
            )

        for source in sources:
            self._check_ip(source)

        def filled(source: Source) -> List[List[str]]:
            result = []
            for record in records:
                row = list(record)
                row[columns["name"]] = source.name
                row[columns["ip"]] = source.ip
                if columns["region"] is not None and source.region:
                    row[columns["region"]] = source.region
                for index, value in values.items():
                    row[index] = value
                result.append(row)
            return result

        if layout == "sheets" and len(sources) > 1:
            sheets = [(source.name, template.header, filled(source)) for source in sources]
        else:
            sheets = [
                (
                    template.name,
                    template.header,
                    [row for source in sources for row in filled(source)],
                )
            ]

        path = self._output_path(template, sources)
        write_workbook(path, sheets)
        total = sum(len(rows) for _, _, rows in sheets)

        for source in sources:
            self.message.info(
                f"{source.name} ({source.ip}{', ' + source.region if source.region else ''}): "
                f"{len(records)} record(s)"
            )
        self.message.success(
            f"Wrote {total} record(s) on {len(sheets)} sheet(s) "
            f"from template '{template.name}' to {path}. "
            "Download it from Tools -> Artifacts."
        )

        self.artifacts["workbook"] = path
        self.outputs["file"] = str(path)
        self.outputs["rows"] = total
        self.outputs["sheets"] = len(sheets)
        self.outputs["template"] = template.name
        self.outputs["sources"] = len(sources)

    def _select_records(self, template: Template) -> List[List[str]]:
        """All records, or the ones `records` names (1-based numbers and ranges)."""

        wanted = self.arguments.get("records")
        if wanted in (None, "", []):
            if not template.rows:
                raise XlGeneratorException(f"Template '{template.name}' has no records.")
            return template.rows

        items = wanted if isinstance(wanted, list) else str(wanted).replace(";", ",").split(",")
        numbers: List[int] = []
        for item in items:
            if isinstance(item, int) and not isinstance(item, bool):
                numbers.append(item)
                continue
            match = RANGE.match(str(item))
            if not match:
                raise XlGeneratorException(
                    f"'{item}' in 'records' is not a record number or range (like 2-5)."
                )
            first = int(match.group(1))
            last = int(match.group(2) or first)
            numbers.extend(range(first, last + 1) if first <= last else range(first, last - 1, -1))

        outside = sorted({number for number in numbers if not 1 <= number <= len(template.rows)})
        if outside:
            raise XlGeneratorException(
                f"Template '{template.name}' has records 1 to {len(template.rows)}; "
                f"there is no record {outside}."
            )
        return [template.rows[number - 1] for number in dict.fromkeys(numbers)]

    def _values(self, template: Template) -> Dict[int, str]:
        """Extra columns set on every record ({"NAT IP": "10.0.0.5"})."""

        values = self.arguments.dictionary("values") or {}
        columns = {_key(column): index for index, column in enumerate(template.header)}
        result = {}
        for column, value in values.items():
            index = columns.get(_key(str(column)))
            if index is None:
                raise XlGeneratorException(
                    f"'values' sets the column '{column}', "
                    f"which template '{template.name}' does not have "
                    f"(columns: {', '.join(template.header)})."
                )
            result[index] = "" if value is None else str(value)
        return result

    def _single_source(self) -> List[Source]:
        name = self.arguments.string("source_name")
        ip = self.arguments.string("source_ip")
        region = self.arguments.string("source_region") or ""
        if (not name or not ip) and self.can_ask:
            # Asked here rather than by the run: only mode single needs them.
            name = name or self.ask("Source name", name="source_name").strip()
            ip = ip or self.ask("Source ip", name="source_ip").strip()
            region = (
                region
                or self.ask(
                    "Source region (optional)",
                    name="source_region",
                    default="",
                    description="Leave empty to skip.",
                ).strip()
            )
        if not name or not ip:
            raise XlGeneratorException(
                "Mode 'single' needs 'source_name' and 'source_ip' "
                "(interactive runs ask for them when they are left empty)."
            )
        return [Source(name, ip, region)]

    def _multiple_sources(self) -> List[Source]:
        sources: List[Source] = []
        raw = self.arguments.get("sources")
        if raw not in (None, "", []):
            sources.extend(self._parse_sources(raw))

        sources_file = self.arguments.path("sources_file")
        if sources_file:
            sources.extend(self._sources_from_table(read_table(Path(sources_file).expanduser())))

        if not sources and self.can_ask:
            answer = self.ask(
                "Sources",
                name="sources",
                description="One source per line (or separated by ';'): name, ip[, region]",
            )
            sources.extend(self._parse_sources(answer))

        if not sources:
            raise XlGeneratorException(
                "Mode 'multiple' needs 'sources' (name, ip[, region] per line) or a 'sources_file'."
            )

        seen = set()
        for source in sources:
            key = (source.name.casefold(), source.ip)
            if key in seen:
                self.message.warning(f"Source {source.name} ({source.ip}) is given more than once.")
            seen.add(key)
        return sources

    @staticmethod
    def _source(values: List[str], where: str) -> Source:
        values = [str(value).strip() for value in values]
        if len(values) < 2 or not values[0] or not values[1]:
            raise XlGeneratorException(
                f"{where}: give at least a name and an ip (name, ip[, region])."
            )
        if len(values) > 3:
            raise XlGeneratorException(f"{where}: too many values; use name, ip[, region].")
        return Source(values[0], values[1], values[2] if len(values) > 2 else "")

    def _parse_sources(self, raw: Any) -> List[Source]:
        """Sources from a list (objects, lists or text) or text with one per line."""

        if isinstance(raw, str):
            lines = [line for line in re.split(r"[\r\n;]+", raw) if line.strip()]
            return [
                self._source(next(iter(parse_csv(line)), []), f"Source {number} ('{line.strip()}')")
                for number, line in enumerate(lines, start=1)
            ]
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            raise XlGeneratorException("'sources' must be a list or text with one source per line.")

        sources = []
        for number, item in enumerate(raw, start=1):
            where = f"Source {number}"
            if isinstance(item, dict):
                fields = {
                    _key(str(key)).replace("source ", ""): value for key, value in item.items()
                }
                values = [
                    fields.get("name") or fields.get("host") or "",
                    fields.get("ip") or "",
                    fields.get("region") or "",
                ]
                sources.append(self._source([v for v in values if v is not None], where))
            elif isinstance(item, list):
                sources.append(self._source(item, where))
            elif isinstance(item, str):
                sources.extend(self._parse_sources(item))
            else:
                raise XlGeneratorException(
                    f"{where} must be an object, a list or 'name, ip[, region]'."
                )
        return sources

    def _sources_from_table(self, rows: List[List[str]]) -> List[Source]:
        """Sources from a CSV/Excel file: with a header (name, ip, region) or plain columns."""

        if not rows:
            return []
        header = [_key(cell).replace("source ", "") for cell in rows[0]]
        if "name" in header and "ip" in header:
            index = {
                field: header.index(field) for field in ("name", "ip", "region") if field in header
            }
            return [
                self._source(
                    [
                        row[index["name"]] if index["name"] < len(row) else "",
                        row[index["ip"]] if index["ip"] < len(row) else "",
                    ]
                    + (
                        [row[index["region"]] if index["region"] < len(row) else ""]
                        if "region" in index
                        else []
                    ),
                    f"Sources file line {number}",
                )
                for number, row in enumerate(rows[1:], start=2)
            ]
        return [
            self._source(row, f"Sources file line {number}")
            for number, row in enumerate(rows, start=1)
        ]

    def _check_ip(self, source: Source) -> None:
        try:
            ipaddress.ip_network(source.ip, strict=False)
        except ValueError:
            self.message.warning(
                f"'{source.ip}' for {source.name} does not look like an IP address or network."
            )

    def _output_path(self, template: Template, sources: List[Source]) -> Path:
        name = self.arguments.string("output_name")
        if not name:
            label = sources[0].name if len(sources) == 1 else f"{len(sources)}-sources"
            name = f"{template.name}-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        name = SAFE_FILE.sub("_", Path(name).name).strip("._") or "records"
        if not name.lower().endswith(".xlsx"):
            name += ".xlsx"

        folder = self.arguments.path("output_dir")
        directory = Path(folder).expanduser() if folder else Path(self.data_directory) / "files"
        path = directory / name
        if path.exists() and not self.arguments.boolean("overwrite", False):
            raise XlGeneratorException(
                f"'{path}' already exists. Set 'overwrite' or choose another 'output_name'."
            )
        return path
