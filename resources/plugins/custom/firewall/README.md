# xl_generator

Generate Excel (`.xlsx`) files from record templates.

A template is a header and a set of static records (for example the ten
firewall rules of `templates/firewall.csv`). The plugin writes the source
name, ip and (optional) region on every record and produces the Excel file,
for one source (`mode: single`) or for several (`mode: multiple`).

Templates are CSV files: edit the shipped ones in the plugin editor (CSV files
open as a spreadsheet), or create new ones with `action: create_template`.

See MAN.md for every argument and examples.
