REPORT_JS = r'''(function () {
    "use strict";

    function data() {
        const node = document.getElementById("report-data");
        if (!node) return null;
        try { return JSON.parse(node.textContent); }
        catch (_) { return null; }
    }

    function escape(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function duration(ms) {
        if (ms === null || ms === undefined) return "—";
        if (ms < 1000) return `${ms} ms`;
        const seconds = ms / 1000;
        if (seconds < 60) return `${seconds.toFixed(1)} s`;
        const minutes = Math.floor(seconds / 60);
        const remaining = Math.round(seconds % 60);
        return `${minutes}m ${remaining}s`;
    }

    function level(value) {
        return ({
            "10": "DEBUG",
            "20": "INFO",
            "30": "WARNING",
            "40": "ERROR",
            "50": "CRITICAL"
        })[String(value ?? "").toUpperCase()] || String(value ?? "");
    }

    function resultRows(value, depth) {
        depth = depth || 0;
        if (value === null || value === undefined) {
            return `<div class="kv"><div class="kv-key">Value</div><div class="kv-value">null</div></div>`;
        }

        if (typeof value !== "object") {
            return `<div class="kv"><div class="kv-key">Value</div><div class="kv-value">${escape(value)}</div></div>`;
        }

        const entries = Array.isArray(value)
            ? value.map((item, index) => [index, item])
            : Object.entries(value);

        if (!entries.length) {
            return `<div class="empty">No data</div>`;
        }

        return entries.map(([key, item]) => {
            const label = escape(formatKey(key));
            if (item && typeof item === "object") {
                return `
                    <div class="kv">
                        <div class="kv-key">${label}</div>
                        <div class="kv-value">${resultRows(item, depth + 1)}</div>
                    </div>`;
            }
            return `
                <div class="kv">
                    <div class="kv-key">${label}</div>
                    <div class="kv-value">${escape(formatValue(item))}</div>
                </div>`;
        }).join("");
    }

    function formatKey(value) {
        return String(value)
            .replaceAll("_", " ")
            .replace(/([a-z])([A-Z])/g, "$1 $2")
            .replace(/\b\w/g, c => c.toUpperCase());
    }

    function formatValue(value) {
        if (value === null || value === undefined) return "—";
        if (typeof value === "boolean") return value ? "Yes" : "No";
        return String(value);
    }

    function openResult(index) {
        const report = data();
        const step = report?.steps?.[index];
        if (!step?.result) return;

        document.getElementById("result-title").textContent =
            `${step.name} — Plugin Result`;

        document.getElementById("result-content").innerHTML =
            resultRows(step.result);

        document.getElementById("result-raw").textContent =
            JSON.stringify(step.result, null, 2);

        document.getElementById("result-modal").classList.add("open");
    }

    function closeResult() {
        document.getElementById("result-modal").classList.remove("open");
    }

    function applyFilters() {
        const query = document.getElementById("report-search").value.toLowerCase().trim();
        const active = document.querySelector(".filter.active");
        const filter = active?.dataset.filter || "all";

        document.querySelectorAll(".step").forEach((node) => {
            const text = node.dataset.search || "";
            const status = node.dataset.status || "";
            const changed = node.dataset.changed === "true";
            const warnings = node.dataset.warnings === "true";
            const errors = node.dataset.errors === "true";

            let matches = filter === "all";
            if (filter === "success") matches = status === "COMPLETED";
            if (filter === "failed") matches = status === "FAILED";
            if (filter === "changed") matches = changed;
            if (filter === "warnings") matches = warnings;
            if (filter === "errors") matches = errors;

            node.classList.toggle("hidden", !(matches && (!query || text.includes(query))));
        });
    }

    function drawPerformance(report) {
        const container = document.getElementById("performance-chart");
        const steps = (report.steps || []).filter(s => Number.isFinite(s.duration_ms));
        if (!steps.length) {
            container.innerHTML = `<div class="empty">No step timing data available.</div>`;
            return;
        }

        const max = Math.max(...steps.map(s => s.duration_ms), 1);
        container.innerHTML = steps.map(step => `
            <div class="bar-row">
                <div>${escape(step.name)}</div>
                <div class="bar"><span style="width:${Math.max(2, (step.duration_ms / max) * 100)}%"></span></div>
                <div>${duration(step.duration_ms)}</div>
            </div>
        `).join("");
    }

    function init() {
        const report = data();
        if (!report) return;

        drawPerformance(report);

        document.querySelectorAll(".filter").forEach(button => {
            button.addEventListener("click", () => {
                document.querySelectorAll(".filter").forEach(b => b.classList.remove("active"));
                button.classList.add("active");
                applyFilters();
            });
        });

        document.getElementById("report-search").addEventListener("input", applyFilters);
        document.querySelectorAll("[data-result-index]").forEach(button => {
            button.addEventListener("click", () => openResult(Number(button.dataset.resultIndex)));
        });

        document.getElementById("result-close").addEventListener("click", closeResult);
        document.getElementById("result-modal").addEventListener("click", event => {
            if (event.target.id === "result-modal") closeResult();
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") closeResult();
        });
    }

    document.addEventListener("DOMContentLoaded", init);
}());
'''
