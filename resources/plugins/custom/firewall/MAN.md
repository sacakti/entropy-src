# xl_generator

Generate Excel (`.xlsx`) files from record templates.

------------------------------------------------------------------------

## Overview

A **template** is a table: the first row names the columns, the next rows are
the **records** that stay the same from one file to the next. The shipped
template `firewall` has ten records with these columns:

```text
Source name, Source ip, Source test region, Destination name, Ip,
Destination region, Port, Service name, Protocol, NAT IP
```

The source columns are empty in the template. When you generate a file, the
plugin writes the source you give on **every** record and saves the result as
an Excel file:

-   **single** mode: one source (`source_name`, `source_ip`, and optionally
    `source_region`) on all records. Ten records in, ten rows out.
-   **multiple** mode: each source gets its own copy of the records. Three
    sources and ten records give thirty rows, on one sheet
    (`layout: rows`) or on one sheet per source (`layout: sheets`).

The Excel file has a bold header, borders, a frozen header row, filter
buttons and fitted column widths. It is written to `files` in the
plugin's data folder (or `output_dir`) and listed in **Tools -> Artifacts**,
where it can be downloaded.

No Python library is needed: the file is written with the standard library.

------------------------------------------------------------------------

## Templates

Templates come from two places:

-   **Shipped with the plugin**: the `.csv` (or `.xlsx`) files in the plugin's
    `templates/` folder. Open the plugin in the plugin editor: CSV files open
    as a spreadsheet, so the static records can be edited like in Excel.
    Add a new `.csv` file there for a new shipped template.
-   **Saved by runs** with `action: create_template`. They are kept in the
    plugin's data folder of the active project
    (`<workspace>/plugin-data/custom.xl_generator/project-<id>/templates`),
    so they survive runs and plugin upgrades, and each project has its own. A saved
    template with the same name as a shipped one is used instead of it.

Any `.csv` or `.xlsx` file on the server can also be used once, with
`template_file`.

The source columns are found by name: the first columns whose names start
with `Source` and contain `name`, `ip` and `region` (case and punctuation do
not matter: `Source IP`, `source_ip` and `Source test region` all match). A
template without a source name or source ip column cannot be used to
generate files. Other columns can be set on every record with `values`.

------------------------------------------------------------------------

## Arguments

  Argument          Type         Default      Used by
  ----------------- ------------ ------------ ------------------------------
  `action`          string       `generate`   all
  `mode`            string       `single`     generate
  `template`        string       `firewall`   generate, create_template
  `template_file`   path         ---          generate, create_template
  `source_name`     string       ---          generate (single)
  `source_ip`       string       ---          generate (single)
  `source_region`   string       ---          generate (single)
  `sources`         any          ---          generate (multiple)
  `sources_file`    path         ---          generate (multiple)
  `layout`          string       `rows`       generate (multiple)
  `records`         any          all          generate
  `values`          dictionary   ---          generate
  `output_name`     string       generated    generate
  `output_dir`      path         data folder  generate
  `overwrite`       boolean      `false`      generate, create_template
  `template_name`   string       ---          create/delete_template
  `columns`         list         ---          create_template
  `rows`            any          ---          create_template

### `action`

-   `generate`: write an Excel file (the default).
-   `create_template`: save a new template (or replace one with `overwrite`).
-   `list_templates`: show every template with its columns and record count.
-   `delete_template`: delete a saved template (`template_name`).

### `source_name`, `source_ip`, `source_region`

Mode `single`. Name and ip are needed; interactive runs ask for them when
they are left empty. The region is optional: when empty, the template's
value is kept. The ip may also be a network (`10.1.0.0/24`); a value that is
neither gives a warning, not an error.

### `sources`

Mode `multiple`. One source per line, or separated by `;`:

```text
web-01, 10.1.1.10, EU
web-02, 10.1.1.11
```

or a list of objects:

```json
[{"name": "web-01", "ip": "10.1.1.10", "region": "EU"}, {"name": "web-02", "ip": "10.1.1.11"}]
```

Interactive runs ask for the sources when neither `sources` nor
`sources_file` is given.

### `sources_file`

Mode `multiple`. A `.csv` or `.xlsx` file of sources: with a header row
naming `name`, `ip` and optionally `region` (or `Source name`, ...), or
without header, columns in that order.

### `records`

Only some of the template's records, by number (1 is the first record under
the header): `"1,3,5-7"` or `[1, 3, 5]`. All records when empty.

### `values`

Other columns written on every record, by column name:
`{"NAT IP": "172.16.0.10"}`.

### `columns`, `rows` (create_template)

-   With `columns`: a new template with these columns, and the records in
    `rows`.
-   Without `columns`: a copy of `template` (or `template_file`); `rows`,
    when given, replaces its records.

`rows` is CSV text (one record per line, values in column order), or a list
of lists, or a list of objects by column name.

------------------------------------------------------------------------

## Outputs

  Output        Type      Description
  ------------- --------- ---------------------------------------------------
  `file`        string    Excel file written / template file saved
  `rows`        integer   Records written / in the template
  `sheets`      integer   Sheets in the Excel file
  `sources`     integer   Sources filled in
  `template`    string    Template used, created or deleted
  `templates`   list      list_templates: each template's name, origin, columns, records

------------------------------------------------------------------------

## Examples

One source on all ten records:

```json
{"plugin": "custom.xl_generator",
 "arguments": {"source_name": "billing-app", "source_ip": "10.50.1.10", "source_region": "EU"}}
```

Three sources, one sheet each, records 1 to 5 only:

```json
{"plugin": "custom.xl_generator",
 "arguments": {"mode": "multiple", "layout": "sheets", "records": "1-5",
               "sources": "app-1, 10.1.1.1, EU\napp-2, 10.1.1.2\napp-3, 10.1.1.3, US"}}
```

A new template from scratch (CSV `rows` follow the column order, so the
source cells stay empty at the start of each line):

```json
{"plugin": "custom.xl_generator",
 "arguments": {"action": "create_template", "template_name": "db-access",
               "columns": ["Source name", "Source ip", "Destination name", "Ip", "Port", "Protocol"],
               "rows": ",,db-primary,10.20.2.21,1521,TCP\n,,db-standby,10.30.2.21,1521,TCP"}}
```

Objects by column name avoid counting commas:

```json
"rows": [{"Destination name": "db-primary", "Ip": "10.20.2.21", "Port": 1521, "Protocol": "TCP"}]
```

A copy of the firewall template with its own name, to change later:

```json
{"plugin": "custom.xl_generator",
 "arguments": {"action": "create_template", "template_name": "firewall-dr", "template": "firewall"}}
```

Use the step output in a later step: `${steps.<step>.outputs.file}`.
