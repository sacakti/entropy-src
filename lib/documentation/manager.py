"""
Entropy documentation manager.
"""

from __future__ import annotations

import hashlib
import markdown
import html
import re
from pathlib import Path


class DocumentationManager:
    """
    Loads Entropy Markdown documentation and generates
    terminal and HTML representations.
    """

    _CHANGELOG_PATTERN = re.compile(
        r"^changelog-(?P<version>\d+(?:\.\d+){1,2})\.md$",
    )

    def __init__(
        self,
        documentation_path: Path,
        generated_path: Path,
    ) -> None:

        self._documentation_path = documentation_path

        self._generated_path = generated_path

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self) -> str:
        """
        Return the complete documentation as Markdown.
        """

        files = self._files()

        if not files:

            raise FileNotFoundError(
                "No Entropy documentation files were found.",
            )

        return "\n\n".join(
            path.read_text(
                encoding="utf-8",
            ).strip()
            for path in files
        ).strip()

    def generate_html(self) -> tuple[Path, bool]:
        """
        Generate support.html when documentation has changed.

        Returns
        -------
        tuple[Path, bool]
            Generated file path and whether the file was regenerated.
        """

        markdown = self.render()

        digest = self._digest(
            markdown,
        )

        output = self._generated_path / "support.html"

        self._generated_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        if output.exists() and self._has_digest(
            output,
            digest,
        ):

            return output, False

        content = self._build_html(
            markdown,
            digest,
        )

        output.write_text(
            content,
            encoding="utf-8",
        )

        return output, True

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def _files(self) -> list[Path]:
        """
        Return documentation files in deterministic order.
        """

        if not self._documentation_path.exists():

            raise FileNotFoundError(
                "Entropy documentation directory does not exist: "
                f"{self._documentation_path}",
            )

        initial = self._documentation_path / "initial.md"

        files: list[Path] = []

        if initial.exists():

            files.append(
                initial,
            )

        changelogs = []

        for path in self._documentation_path.glob(
            "changelog-*.md",
        ):

            match = self._CHANGELOG_PATTERN.match(
                path.name,
            )

            if match is None:

                continue

            version = tuple(
                int(part)
                for part in match.group(
                    "version",
                ).split(".")
            )

            changelogs.append(
                (
                    version,
                    path,
                ),
            )

        changelogs.sort(
            key=lambda item: item[0],
        )

        files.extend(
            path
            for _, path in changelogs
        )

        return files

    # ------------------------------------------------------------------
    # Hash
    # ------------------------------------------------------------------

    @staticmethod
    def _digest(
        content: str,
    ) -> str:
        """
        Calculate a deterministic documentation digest.
        """

        return hashlib.sha256(
            content.encode(
                "utf-8",
            ),
        ).hexdigest()

    # ------------------------------------------------------------------
    # Existing HTML
    # ------------------------------------------------------------------

    @staticmethod
    def _has_digest(
        path: Path,
        digest: str,
    ) -> bool:
        """
        Return True when generated HTML contains the expected digest.
        """

        try:

            content = path.read_text(
                encoding="utf-8",
            )

        except OSError:

            return False

        return (
            f'<meta name="entropy-documentation-hash" '
            f'content="{digest}">'
        ) in content

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _build_html(
        self,
        markdown_content: str,
        digest: str,
    ) -> str:
        """
        Build a standalone HTML document.
        """

        body = markdown.markdown(
            markdown_content,
            extensions=[
                "fenced_code",
                "tables",
                "toc",
            ],
        )

        return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <meta
        name="entropy-documentation-hash"
        content="{digest}"
    >

    <title>Entropy Documentation</title>

    <style>

    :root {{
        color-scheme: light;
    }}

    html {{
        scroll-behavior: smooth;
    }}

    body {{
        margin: 0;
        padding: 0;
        background: #ffffff;
        color: #1f2328;
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            Helvetica,
            Arial,
            sans-serif;
        line-height: 1.6;
    }}

    main {{
        width: min(1100px, calc(100% - 48px));
        margin: 0 auto;
        padding: 48px 0 80px;
    }}

    h1,
    h2,
    h3,
    h4,
    h5,
    h6 {{
        line-height: 1.25;
        margin-top: 2em;
        margin-bottom: 0.7em;
    }}

    h1 {{
        font-size: 2.2rem;
        margin-top: 0;
    }}

    h2 {{
        font-size: 1.7rem;
    }}

    h3 {{
        font-size: 1.35rem;
    }}

    p {{
        margin: 0 0 1rem;
    }}

    ul,
    ol {{
        margin-top: 0.5rem;
        margin-bottom: 1rem;
        padding-left: 2rem;
    }}

    li {{
        margin: 0.25rem 0;
    }}

    blockquote {{
        margin: 1.5rem 0;
        padding: 0.75rem 1.25rem;
        border-left: 4px solid #888;
        background: #f6f8fa;
    }}

    code {{
        font-family:
            "SFMono-Regular",
            Consolas,
            "Liberation Mono",
            monospace;
    }}

    :not(pre) > code {{
        padding: 0.15em 0.35em;
        border-radius: 4px;
        background: #f0f0f0;
    }}

    pre {{
        margin: 1.25rem 0;
        padding: 1rem;
        overflow-x: auto;
        border-radius: 6px;
        background: #f6f8fa;
    }}

    pre code {{
        padding: 0;
        background: transparent;
    }}

    hr {{
        margin: 2.5rem 0;
        border: 0;
        border-top: 1px solid #d0d7de;
    }}

    table {{
        width: 100%;
        margin: 1.5rem 0;
        border-collapse: collapse;
    }}

    th,
    td {{
        padding: 8px 12px;
        border: 1px solid #d0d7de;
        text-align: left;
    }}

    th {{
        font-weight: 600;
        background: #f6f8fa;
    }}

    a {{
        color: inherit;
    }}

    #toc {{
        margin: 2rem 0;
        padding: 1.25rem 1.5rem;
        border: 1px solid #d0d7de;
        border-radius: 6px;
        background: #f6f8fa;
    }}

    </style>
    </head>

    <body>

    <main>
    {body}
    </main>

    </body>
    </html>
    """
