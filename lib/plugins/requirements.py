"""
Command line tools a plugin needs on the machine it runs on ("system_requirements" in
plugin.json), for showing to people. Nothing here stops a plugin from running.

    "system_requirements": [
        {"name": "oc", "note": "OpenShift command line client."},
        {"name": "git", "optional": true, "note": "Only for repository sources."}
    ]
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List


def tool_available(name: str) -> bool:
    """Whether this machine has the tool; SQL*Plus may also be in ORACLE_HOME."""

    if shutil.which(name):
        return True
    home = os.environ.get("ORACLE_HOME")
    return bool(name == "sqlplus" and home and (Path(home) / "bin" / "sqlplus").is_file())


def system_requirements(manifest: Any) -> List[Dict[str, Any]]:
    """The tools a manifest declares; what is malformed is left out, as for other dependencies."""

    declared = manifest.get("system_requirements") if isinstance(manifest, dict) else None
    tools: List[Dict[str, Any]] = []

    for item in declared if isinstance(declared, list) else []:
        entry = {"name": item} if isinstance(item, str) else item
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name = entry["name"].strip()
        if not name:
            continue
        tools.append(
            {
                "name": name,
                "optional": bool(entry.get("optional", False)),
                "note": str(entry.get("note") or ""),
                "available": tool_available(name),
            }
        )

    return tools
