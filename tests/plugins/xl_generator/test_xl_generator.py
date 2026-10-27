"""
Tests for the xl_generator plugin: templates, sources and the .xlsx files.
"""

from __future__ import annotations

import zipfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from lib.plugins.arguments import PluginArguments
from resources.plugins.custom.xl_generator.exceptions import XlGeneratorException
from resources.plugins.custom.xl_generator.plugin import XlGeneratorPlugin, source_columns
from resources.plugins.custom.xl_generator.xlsx import read_first_sheet, write_workbook

HEADER = [
    "Source name",
    "Source ip",
    "Source test region",
    "Destination name",
    "Ip",
    "Destination region",
    "Port",
    "Service name",
    "Protocol",
    "NAT IP",
]


def run(tmp_path: Path, interactive: bool = False, answer: str = "", **arguments):
    context = Mock()
    context.arguments = PluginArguments(arguments)
    context.outputs = {}
    context.artifacts = {}
    context.workspace = tmp_path / "run"
    context.data_directory = tmp_path
    context.can_ask = interactive
    context.ask.return_value = answer
    context.activity.return_value = nullcontext()
    plugin = XlGeneratorPlugin(context)
    result = plugin.execute()
    return result, context


def sheets(path: Path):
    with zipfile.ZipFile(path) as archive:
        workbook = archive.read("xl/workbook.xml").decode()
        count = len([name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")])
    return workbook, count


def test_single_source_fills_every_record(tmp_path: Path) -> None:
    result, context = run(
        tmp_path,
        source_name="billing",
        source_ip="10.50.1.10",
        source_region="EU",
        output_name="out",
    )

    path = tmp_path / "files" / "out.xlsx"
    assert result.success and context.outputs["file"] == str(path)
    assert context.artifacts["workbook"] == path
    rows = read_first_sheet(path)
    assert rows[0] == HEADER
    assert len(rows) == 11 and context.outputs["rows"] == 10
    assert all(row[:3] == ["billing", "10.50.1.10", "EU"] for row in rows[1:])
    # Static values of the template are kept; ports stay numbers.
    assert rows[1][3:8] == ["app-server-01", "10.20.1.11", "DC1", "443", "HTTPS"]
    assert rows[9][9] == "172.16.5.22"


def test_region_is_optional(tmp_path: Path) -> None:
    run(tmp_path, source_name="a", source_ip="10.0.0.1", output_name="out")

    rows = read_first_sheet(tmp_path / "files" / "out.xlsx")
    assert rows[1][:2] == ["a", "10.0.0.1"] and rows[1][2] == ""


def test_single_needs_name_and_ip(tmp_path: Path) -> None:
    with pytest.raises(XlGeneratorException, match="source_name"):
        run(tmp_path, source_name="a")


def test_multiple_sources_stacked_or_one_sheet_each(tmp_path: Path) -> None:
    sources = "web-01, 10.1.1.10, EU\nweb-02, 10.1.1.11; web-03,10.1.1.12,US"
    _, context = run(
        tmp_path, mode="multiple", sources=sources, records="1-2,9", output_name="rows"
    )

    rows = read_first_sheet(tmp_path / "files" / "rows.xlsx")
    assert context.outputs["rows"] == 9 and context.outputs["sources"] == 3
    assert [row[0] for row in rows[1:]] == ["web-01"] * 3 + ["web-02"] * 3 + ["web-03"] * 3
    assert [row[3] for row in rows[1:4]] == ["app-server-01", "app-server-02", "sftp-gateway"]

    _, context = run(
        tmp_path,
        mode="multiple",
        layout="sheets",
        sources=[{"name": "web-01", "ip": "10.1.1.10"}, ["web-02", "10.1.1.11", "US"]],
        output_name="sheets",
    )
    workbook, count = sheets(tmp_path / "files" / "sheets.xlsx")
    assert count == 2 and context.outputs["sheets"] == 2
    assert 'name="web-01"' in workbook and 'name="web-02"' in workbook


def test_multiple_sources_from_file_and_interactive_answer(tmp_path: Path) -> None:
    listing = tmp_path / "sources.csv"
    listing.write_text("Source name;Source ip;Region\nalpha;10.9.0.1;EU\nbeta;10.9.0.2;\n")
    _, context = run(tmp_path, mode="multiple", sources_file=str(listing), output_name="file")
    rows = read_first_sheet(tmp_path / "files" / "file.xlsx")
    assert context.outputs["sources"] == 2
    assert rows[1][:3] == ["alpha", "10.9.0.1", "EU"] and rows[11][:3] == ["beta", "10.9.0.2", ""]

    _, context = run(
        tmp_path, interactive=True, answer="gamma,10.9.0.3", mode="multiple", output_name="ask"
    )
    assert context.ask.called and context.outputs["sources"] == 1


def test_values_and_unknown_columns(tmp_path: Path) -> None:
    run(
        tmp_path,
        source_name="a",
        source_ip="10.0.0.1",
        values={"nat ip": "1.2.3.4"},
        output_name="v",
    )
    rows = read_first_sheet(tmp_path / "files" / "v.xlsx")
    assert {row[9] for row in rows[1:]} == {"1.2.3.4"}

    with pytest.raises(XlGeneratorException, match="does not have"):
        run(tmp_path, source_name="a", source_ip="10.0.0.1", values={"Nope": "x"})


def test_records_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(XlGeneratorException, match="no record"):
        run(tmp_path, source_name="a", source_ip="10.0.0.1", records=[11])


def test_existing_file_needs_overwrite(tmp_path: Path) -> None:
    run(tmp_path, source_name="a", source_ip="10.0.0.1", output_name="same")
    with pytest.raises(XlGeneratorException, match="already exists"):
        run(tmp_path, source_name="a", source_ip="10.0.0.1", output_name="same")
    run(tmp_path, source_name="a", source_ip="10.0.0.1", output_name="same", overwrite=True)


def test_create_list_use_and_delete_templates(tmp_path: Path) -> None:
    _, context = run(
        tmp_path,
        action="create_template",
        template_name="db-access",
        columns=["Source name", "Source ip", "Destination name", "Port"],
        rows=[{"Destination name": "db-primary", "Port": 1521}, ",,db-standby,1521"],
    )
    assert context.outputs["rows"] == 2
    assert (tmp_path / "templates" / "db-access.csv").read_text().splitlines() == [
        "Source name,Source ip,Destination name,Port",
        ",,db-primary,1521",
        ",,db-standby,1521",
    ]

    with pytest.raises(XlGeneratorException, match="already exists"):
        run(tmp_path, action="create_template", template_name="db-access", columns=["Source name"])

    # A copy of the shipped template.
    run(tmp_path, action="create_template", template_name="firewall-dr", template="firewall")
    _, context = run(tmp_path, action="list_templates")
    listed = {item["name"]: item for item in context.outputs["templates"]}
    assert listed["firewall"]["origin"] == "plugin" and listed["firewall"]["records"] == 10
    assert listed["db-access"]["origin"] == "saved" and listed["firewall-dr"]["records"] == 10

    _, context = run(
        tmp_path, template="db-access", source_name="app", source_ip="10.1.0.0/24", output_name="db"
    )
    rows = read_first_sheet(tmp_path / "files" / "db.xlsx")
    assert rows == [
        ["Source name", "Source ip", "Destination name", "Port"],
        ["app", "10.1.0.0/24", "db-primary", "1521"],
        ["app", "10.1.0.0/24", "db-standby", "1521"],
    ]

    run(tmp_path, action="delete_template", template_name="db-access")
    with pytest.raises(XlGeneratorException, match="No template 'db-access'"):
        run(tmp_path, template="db-access", source_name="a", source_ip="10.0.0.1")
    with pytest.raises(XlGeneratorException, match="No saved template"):
        run(tmp_path, action="delete_template", template_name="firewall")


def test_template_without_source_columns(tmp_path: Path) -> None:
    template = tmp_path / "plain.csv"
    template.write_text("Host,Port\nx,1\n")
    with pytest.raises(XlGeneratorException, match="no source name or source ip column"):
        run(tmp_path, template_file=str(template), source_name="a", source_ip="10.0.0.1")


def test_xlsx_template_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    write_workbook(
        path,
        [
            (
                "A sheet: with/odd*chars",
                ["Source name", "Source ip", "Note"],
                [["", "", 'say "hi" & <go>\nnow'], ["", "", "007"]],
            )
        ],
    )
    assert read_first_sheet(path) == [
        ["Source name", "Source ip", "Note"],
        ["", "", 'say "hi" & <go>\nnow'],
        ["", "", "007"],
    ]

    _, context = run(
        tmp_path,
        template_file=str(path),
        source_name="s",
        source_ip="10.0.0.9",
        output_name="from-xlsx",
    )
    assert read_first_sheet(Path(context.outputs["file"]))[2] == ["s", "10.0.0.9", "007"]


def test_source_columns_by_name() -> None:
    assert source_columns(HEADER) == {"name": 0, "ip": 1, "region": 2}
    assert source_columns(["Dest", "SRC_IP", "source-name"]) == {"name": 2, "ip": 1, "region": None}


def test_interactive_single_asks_for_what_is_missing(tmp_path: Path) -> None:
    context = Mock()
    context.arguments = PluginArguments({"output_name": "asked"})
    context.outputs, context.artifacts, context.data_directory = {}, {}, tmp_path
    context.can_ask = True
    context.ask.side_effect = ["billing", "10.50.1.10", ""]
    context.activity.return_value = nullcontext()
    XlGeneratorPlugin(context).execute()

    assert [call.kwargs["name"] for call in context.ask.call_args_list] == [
        "source_name",
        "source_ip",
        "source_region",
    ]
    assert read_first_sheet(tmp_path / "files" / "asked.xlsx")[1][:3] == [
        "billing",
        "10.50.1.10",
        "",
    ]
