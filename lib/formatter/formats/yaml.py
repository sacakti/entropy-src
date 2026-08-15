"""
YAML formatter.
"""

from __future__ import annotations

from typing import Any

import yaml

from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import FormatterFormatError


class _EntropyYamlDumper(
    yaml.SafeDumper,
):
    """
    YAML dumper with Entropy formatting rules.
    """


def _represent_multiline_string(
    dumper: _EntropyYamlDumper,
    value: str,
):
    """
    Represent multiline strings using YAML block style.
    """

    if "\n" not in value:

        return dumper.represent_scalar(
            "tag:yaml.org,2002:str",
            value,
        )

    value = value.rstrip("\n")

    return dumper.represent_scalar(
        "tag:yaml.org,2002:str",
        value,
        style="|",
    )


_EntropyYamlDumper.add_representer(
    str,
    _represent_multiline_string,
)


class YamlFormatter(
    BaseFormatter,
):
    """
    Format YAML documents.
    """

    @property
    def name(
        self,
    ) -> str:
        return "yaml"

    @property
    def aliases(
        self,
    ) -> tuple[str, ...]:
        return (
            "yml",
        )

    def format(
        self,
        content: str,
    ) -> str:
        """
        Parse and format YAML.
        """

        if not content.strip():

            raise FormatterFormatError(
                "Invalid YAML: document is empty.",
            )

        try:

            document: Any = yaml.safe_load(
                content,
            )

        except yaml.YAMLError as exc:

            raise FormatterFormatError(
                f"Invalid YAML: {exc}",
            ) from exc

        if document is None:

            raise FormatterFormatError(
                "Invalid YAML: document does not contain "
                "a YAML value.",
            )

        try:

            formatted = yaml.dump(
                document,
                Dumper=_EntropyYamlDumper,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                indent=2,
                width=120,
            )

        except yaml.YAMLError as exc:

            raise FormatterFormatError(
                f"Unable to format YAML: {exc}",
            ) from exc

        if not formatted.strip():

            raise FormatterFormatError(
                "Unable to format YAML: formatter produced "
                "an empty document.",
            )

        return formatted
