"""
Process monitor plugin.

An example app plugin: plugin.json declares an "app" page (inputs and
views) and execute() runs a loop with `self.app` that refreshes the view
until the user stops it on the run screen. Automated runs make one pass.
"""

from __future__ import annotations

from typing import Any, Dict, List

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import ProcessMonitorException

SORT_KEYS = {
    "CPU": (lambda row: row["cpu"], True),
    "Memory": (lambda row: row["memory"], True),
    "Name": (lambda row: row["command"].lower(), False),
    "PID": (lambda row: row["pid"], False),
}


class ProcessMonitorPlugin(
    BasePlugin,
):
    """
    Live, filterable process list of the Entropy server.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Refresh the process table until the app is stopped.
        """

        try:
            count = self._monitor()
        except ProcessMonitorException as error:
            return PluginResult(success=False, errors=[str(error)])

        self.outputs["process_count"] = count
        return PluginResult(success=True, changed=False, outputs=dict(self.outputs))

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _monitor(
        self,
    ) -> int:
        """
        The app loop; returns the matching process count of the last refresh.
        """

        max_rows = self.arguments.integer("max_rows", 200, minimum=1, maximum=5000) or 200
        me = self.environment.getenv("USER") or ""
        count = 0

        if self.app.interactive:
            self.message.info("Live page open: use the App tab, and Stop app to finish.")
        self.app.log("activity", "Monitoring started.")

        while self.app.running:
            processes = self._processes()
            wanted = str(self.app.input("filter", "")).strip().lower()
            only_mine = bool(self.app.input("only_mine", False))
            rows = [
                row
                for row in processes
                if (not wanted or wanted in row["command"].lower() or wanted in row["user"].lower())
                and (not only_mine or row["user"] == me)
            ]
            key, descending = SORT_KEYS.get(str(self.app.input("sort", "CPU")), SORT_KEYS["CPU"])
            rows.sort(key=key, reverse=descending)
            count = len(rows)

            self.app.stats(
                "summary",
                {
                    "Processes": len(processes),
                    "Matching": count,
                    "CPU % (matching)": round(sum(row["cpu"] for row in rows), 1),
                    "Memory % (matching)": round(sum(row["memory"] for row in rows), 1),
                },
            )
            self.app.table("processes", rows[:max_rows])

            for press in self.app.events("inspect"):
                self._inspect(press.selection, press.user)

            self.app.wait()

        self.app.log("activity", "Monitoring stopped.")
        self.message.success(f"Process monitor finished: {count} matching processes.")
        return count

    def _processes(
        self,
    ) -> List[Dict[str, Any]]:
        """
        Processes from `ps` (Linux and macOS).
        """

        result = self.shell.run(
            [
                "ps",
                "-eo",
                "pid=,user=,pcpu=,pmem=,comm=",
            ],
        )
        if not result.success:
            raise ProcessMonitorException(f"ps failed: {result.stderr.strip() or result.exit_code}")

        rows = []
        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            try:
                rows.append(
                    {
                        "pid": int(parts[0]),
                        "user": parts[1],
                        "cpu": float(parts[2]),
                        "memory": float(parts[3]),
                        "command": parts[4],
                    }
                )
            except ValueError:
                continue
        return rows

    def _inspect(
        self,
        selection: List[Any],
        user: Any,
    ) -> None:
        """
        Log the full command line of the selected processes.
        """

        pids = [str(int(pid)) for pid in selection if str(pid).isdigit()][:20]
        if not pids:
            self.app.log("activity", "Inspect: select one or more processes first.")
            return
        result = self.shell.run(
            [
                "ps",
                "-o",
                "pid=,args=",
                "-p",
                ",".join(pids),
            ],
        )
        self.app.log("activity", f"Inspect requested by {user or 'someone'}:")
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        self.app.log("activity", *(lines or ["The selected processes have ended."]))
