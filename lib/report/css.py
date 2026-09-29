REPORT_CSS = r"""
:root {
    --bg: #f4f6f8;
    --surface: #ffffff;
    --border: #dfe3e8;
    --text: #17202a;
    --muted: #68737d;
    --success: #197a43;
    --danger: #c62828;
    --warning: #a15c00;
    --info: #2468a2;
    --shadow: 0 2px 10px rgba(0,0,0,.06);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); }
button, input { font: inherit; }
#app { max-width: 1440px; margin: auto; padding: 28px; }

.page-header {
    display:flex; justify-content:space-between; gap:24px;
    align-items:flex-start; margin-bottom:22px;
}
.brand {
    font-size:12px; font-weight:800; letter-spacing:.12em;
    text-transform:uppercase; color:var(--muted);
}
h1 { margin:6px 0; font-size:30px; }
h2 { margin:0; font-size:19px; }
h3 { margin:0 0 12px; font-size:15px; }
.execution-id, .muted {
    color:var(--muted);
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:12px;
}

.execution-meta {
    display:grid;
    grid-template-columns:minmax(180px, auto) minmax(300px, 1fr);
    gap:10px;
    margin:16px 0;
}

.header-info {
    display:flex;
    flex-direction:column;
    gap:4px;
    padding:11px 13px;
    background:#f7f8fa;
    border:1px solid var(--border);
    border-radius:8px;
    min-width:0;
}

.header-label {
    font-size:11px;
    color:var(--muted);
    text-transform:uppercase;
    letter-spacing:.06em;
    font-weight:750;
}

.identity-id {
    color:var(--muted);
    font-size:11px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-weight:500;
}

.workspace-info code {
    display:block;
    overflow-wrap:anywhere;
    word-break:break-word;
    font:12px ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--text);
}

.status {
    padding:8px 14px;
    border-radius:999px;
    font-weight:800;
    font-size:13px;
}
.status-success, .status-completed {
    color:var(--success); background:#e7f5ed;
}
.status-failed {
    color:var(--danger); background:#fdeaea;
}
.status-cancelled, .status-skipped {
    color:var(--warning); background:#fff3df;
}
.status-running {
    color:var(--info); background:#e8f2fb;
}

.section { margin-bottom:28px; }
.section-title {
    display:flex; justify-content:space-between; align-items:center;
    gap:12px; margin-bottom:12px;
}
.cards {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr));
    gap:10px;
}
.card, .step, .metric, .chart-container, .failure {
    background:var(--surface); border:1px solid var(--border);
    border-radius:10px;
}
.card { padding:16px; }
.card-label, .metric span { font-size:12px; color:var(--muted); }
.card-value { font-size:23px; font-weight:800; margin-top:5px; }

.failure {
    border-left:4px solid var(--danger);
    background:#fff7f7;
    padding:16px 18px;
}
.failure-title { color:var(--danger); font-weight:800; margin-bottom:7px; }
.failure-message { margin-top:8px; font-size:14px; }
.failure-meta {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:10px; margin-top:14px;
}
.failure-meta div { background:#fff; padding:10px; border-radius:7px; }
.failure-meta label {
    display:block; font-size:11px; color:var(--muted); margin-bottom:4px;
}
.failure-detail {
    background:#fff7f7; border:1px solid #f2d4d4;
    border-radius:8px; padding:14px;
}
.failure-detail .exception {
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:13px; white-space:pre-wrap; overflow-wrap:anywhere;
}

.performance-grid {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:10px; margin-bottom:12px;
}
.metric { padding:16px; }
.metric strong { display:block; margin-top:5px; font-size:19px; }
.chart-container { padding:18px; }
.chart { min-height:160px; overflow:auto; }
.chart-empty { padding:40px; text-align:center; color:var(--muted); }

.filters { display:flex; flex-wrap:wrap; gap:6px; }
.filter, .action {
    border:1px solid var(--border); background:#fff;
    padding:7px 11px; border-radius:7px; cursor:pointer; font-size:12px;
}
.filter.active { background:var(--text); color:#fff; }
.search { margin-bottom:12px; }
.search input {
    width:100%; padding:10px 12px;
    border:1px solid var(--border); border-radius:7px;
}

.step { margin-bottom:10px; overflow:hidden; background:#fff; }
.step-header {
    display:flex; justify-content:space-between; align-items:center;
    gap:15px; padding:14px 17px; cursor:pointer;
}
.step-title { display:flex; align-items:center; gap:10px; font-weight:750; }
.step-index {
    width:28px; height:28px; border-radius:50%;
    background:#edf0f3; display:grid; place-items:center;
    font-size:12px; font-weight:800; flex-shrink:0;
}
.step-meta {
    display:flex; align-items:center; gap:10px;
    font-size:12px; color:var(--muted);
}
.step-body {
    display:none; padding:0 17px 18px;
    border-top:1px solid #edf0f3;
}
.step.open .step-body { display:block; }
.step-info {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:10px; padding:16px 0;
}
.step-info > div {
    background:#f7f8fa; padding:10px; border-radius:7px;
}
.step-info span {
    display:block; font-size:11px; color:var(--muted); margin-bottom:4px;
}

.detail-block { margin-top:14px; }
.detail-title { font-size:14px; font-weight:750; margin-bottom:8px; }

.message {
    padding:9px 11px; border-radius:7px; margin:6px 0;
    font-size:13px; border-left:3px solid var(--border);
    background:#fafafa;
}
.message.WARNING { border-left-color:var(--warning); }
.message.ERROR, .message.CRITICAL { border-left-color:var(--danger); }
.message.INFO { border-left-color:var(--info); }
.message.DEBUG { border-left-color:var(--border); }
.level {
    display: inline-block;
    font-size: 10px;
    font-weight: 800;
    margin-right: 8px;
    min-width: 34px;
}

.tree {
    border-left:2px solid #e5e8eb; margin-left:8px; padding-left:15px;
}
.stage {
    padding:10px; background:#f7f8fa; border-radius:7px; margin:8px 0;
}
.stage-header, .activity {
    display:flex; justify-content:space-between; gap:12px;
}
.activity { padding:7px 0 0 12px; font-size:13px; }

/* Execution Timeline */

.execution-timeline {
    position:relative;
    padding:8px 0 4px;
}

/*
 * The generic .step rule is also used by the timeline nodes.  Reset the
 * properties that belong to the old step-card layout so the timeline node
 * itself stays transparent and only .timeline-card is rendered as a card.
 */
.timeline-node.step {
    display:grid;
    grid-template-columns:32px minmax(0, 1fr);
    gap:16px;
    align-items:stretch;
    margin:0 0 16px;
    padding:0;
    border:0;
    border-radius:0;
    background:transparent;
    box-shadow:none;
    overflow:visible;
}

.timeline-marker {
    position:relative;
    display:flex;
    justify-content:center;
    align-items:flex-start;
    min-height:100%;
}

.timeline-dot {
    position:relative;
    z-index:3;
    width:22px;
    height:22px;
    margin-top:17px;
    border-radius:50%;
    border:2px solid var(--success);
    background:#fff;
    box-sizing:border-box;
    flex:0 0 22px;
}

.timeline-dot::after {
    content:"";
    position:absolute;
    width:8px;
    height:8px;
    left:50%;
    top:50%;
    transform:translate(-50%,-50%);
    border-radius:50%;
    background:var(--success);
}

/* Inner status dot */
.timeline-dot::after {
    content:"";
    position:absolute;
    width:8px;
    height:8px;
    left:50%;
    top:50%;
    transform:translate(-50%,-50%);
    border-radius:50%;
    background:var(--success);
}

/* Vertical connector */
.timeline-line {
    position:absolute;
    z-index:1;
    top:39px;
    bottom:-14px;
    left:50%;
    width:3px;
    transform:translateX(-50%);
    background:#d9dee5;
}

.timeline-card {
    min-width:0;
    border:1px solid #d9dee5;
    border-radius:12px;
    background:#fff;
    box-shadow:0 1px 3px rgba(0,0,0,.05);
    overflow:hidden;
}

.timeline-card-header {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:20px;
    min-height:68px;
    padding:14px 20px;
    cursor:pointer;
}

.timeline-header-actions {
    display:flex;
    align-items:center;
    justify-content:flex-end;
    gap:8px;
    flex:0 0 auto;
}

.timeline-step {
    display:flex;
    align-items:center;
    gap:11px;
    min-width:0;
    flex:1 1 auto;
}

.timeline-step > div:last-child {
    min-width:0;
}

.timeline-index {
    width:30px;
    height:30px;
    display:grid;
    place-items:center;
    flex:0 0 30px;
    border-radius:50%;
    background:#edf0f3;
    color:var(--text);
    font-size:11px;
    font-weight:800;
}

.timeline-plugin {
    margin-top:3px;
    color:var(--muted);
    font-size:11px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    overflow-wrap:anywhere;
}

.timeline-status {
    flex:0 0 auto;
    padding:5px 9px;
    border-radius:999px;
    font-size:10px;
    font-weight:800;
    letter-spacing:.04em;
    white-space:nowrap;
}

.timeline-result {
    flex:0 0 auto;
    white-space:nowrap;
}

.timeline-result:hover {
    background:#f4f6f8;
}

.timeline-duration {
    display:grid;
    grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
    align-items:center;
    column-gap:24px;
    min-height:58px;
    padding:12px 20px 14px;
    border-top:1px solid #e5e7eb;
}

.timeline-metric {
    min-width:0;
}

.timeline-metric:last-child {
    text-align:left;
}

.timeline-metric span {
    display:block;
    margin-bottom:3px;
    color:var(--muted);
    font-size:10px;
    line-height:1.2;
    text-transform:uppercase;
    letter-spacing:.06em;
    font-weight:750;
}

.timeline-metric strong {
    display:block;
    color:var(--text);
    font:12px ui-monospace,SFMono-Regular,Menlo,monospace;
    white-space:nowrap;
}

.timeline-duration-value {
    display:flex;
    align-items:center;
    justify-content:center;
    gap:10px;
    min-width:110px;
    white-space:nowrap;
}

.timeline-duration-value strong {
    color:#155a91;
    white-space:nowrap;
    font-size:13px;
}

.timeline-duration-line {
    width:40px;
    height:2px;
    flex:0 0 40px;
    background:var(--info);
    border-radius:2px;
}

.timeline-summary {
    color:var(--muted);
    font-size:12px;
}

/* Expanded timeline content */

.timeline-card .step-body {
    display:none;
    padding:0 20px 20px;
    border-top:1px solid #edf0f3;
}

.timeline-card .step.open .step-body,
.timeline-node.step.open .step-body {
    display:block;
}

.timeline-card .step-info {
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:10px;
    padding:16px 0 4px;
}

.timeline-card .step-info > div {
    min-width:0;
    background:#f7f8fa;
    padding:10px;
    border-radius:7px;
}

/* Timeline status states */

/* Completed */
.timeline-node.completed .timeline-dot {
    border-color:var(--success);
}

.timeline-node.completed .timeline-dot::after {
    background:var(--success);
}

.timeline-node.completed .timeline-status {
    color:var(--success);
    background:#e7f5ed;
}

/* Failed */
.timeline-node.failed .timeline-dot {
    border-color:var(--danger);
}

.timeline-node.failed .timeline-dot::after {
    background:var(--danger);
}

.timeline-node.failed .timeline-status {
    color:var(--danger);
    background:#fdeaea;
}

/* Skipped / Cancelled */
.timeline-node.cancelled .timeline-dot,
.timeline-node.skipped .timeline-dot {
    border-color:var(--warning);
}

.timeline-node.cancelled .timeline-dot::after,
.timeline-node.skipped .timeline-dot::after {
    background:var(--warning);
}

.timeline-node.cancelled .timeline-status,
.timeline-node.skipped .timeline-status {
    color:var(--warning);
    background:#fff3df;
}

/* Running */
.timeline-node.running .timeline-dot {
    border-color:var(--info);
}

.timeline-node.running .timeline-dot::after {
    background:var(--info);
}

.timeline-node.running .timeline-status {
    color:var(--info);
    background:#e8f2fb;
}

.modal-backdrop {
    position:fixed; inset:0; background:rgba(0,0,0,.45);
    display:none; align-items:center; justify-content:center;
    padding:25px; z-index:100;
}
.modal-backdrop.open { display:flex; }
.modal {
    width:min(980px,100%);
    max-height:90vh;
    overflow:hidden;
    background:#fff;
    border-radius:14px;
    box-shadow:0 20px 60px rgba(0,0,0,.28);
}

.modal-head {
    padding:18px 22px;
    border-bottom:1px solid var(--border);
    display:flex;
    justify-content:space-between;
    align-items:center;
    background:#fff;
}

.modal-body {
    padding:22px;
    overflow:auto;
    max-height:calc(90vh - 72px);
}
.close {
    border:0; background:transparent; font-size:24px; cursor:pointer;
}
.result-tabs { display:flex; gap:6px; margin-bottom:14px; }
.result-tab {
    border:1px solid var(--border); background:#fff;
    border-radius:7px; padding:7px 12px; cursor:pointer; font-size:12px;
}
.result-tab.active { background:var(--text); color:#fff; }

/* Plugin Result Pretty View */

.result-object {
    display:flex;
    flex-direction:column;
    gap:10px;
}

.result-field {
    display:grid;
    grid-template-columns:190px minmax(0,1fr);
    border:1px solid var(--border);
    border-radius:9px;
    overflow:hidden;
    background:#fff;
}

.result-field-label {
    display:flex;
    align-items:center;
    padding:13px 15px;
    background:#f6f8fa;
    color:#46515b;
    font-size:13px;
    font-weight:750;
}

.result-field-value {
    display:flex;
    align-items:center;
    min-width:0;
    padding:13px 15px;
    font-size:13px;
    overflow-wrap:anywhere;
}

.result-field-object {
    display:block;
}

.result-field-object > .result-field-label {
    border-bottom:1px solid var(--border);
}

.result-field-object > .result-field-value {
    padding:10px;
    background:#fbfcfd;
}

.result-value {
    padding:4px 0;
}

.result-value-text {
    overflow-wrap:anywhere;
}

.result-empty {
    padding:12px 14px;
    border:1px dashed var(--border);
    border-radius:8px;
    background:#fafbfc;
    color:var(--muted);
    font-size:13px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
}

.result-bool {
    display:inline-flex;
    align-items:center;
    padding:4px 9px;
    border-radius:999px;
    font-size:11px;
    font-weight:800;
    line-height:1;
}

.result-bool.true {
    color:var(--success);
    background:#e7f5ed;
}

.result-bool.false {
    color:var(--danger);
    background:#fdeaea;
}

.result-list {
    display:flex;
    flex-direction:column;
    gap:7px;
    width:100%;
}

.result-list-item {
    display:flex;
    align-items:flex-start;
    gap:10px;
    padding:10px 12px;
    border:1px solid var(--border);
    border-radius:8px;
    background:#fff;
}

.result-list-index {
    flex:0 0 22px;
    height:22px;
    display:grid;
    place-items:center;
    border-radius:50%;
    background:#edf0f3;
    color:#596570;
    font-size:10px;
    font-weight:800;
}

.result-list-content {
    min-width:0;
    flex:1;
    overflow-wrap:anywhere;
}

.raw-result { display:none; }
.raw-result pre {
    margin:0; max-height:500px; overflow:auto;
    background:var(--text); color:#e9eef2; padding:14px;
    border-radius:8px; font-size:12px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
}

@media(max-width:700px) {
    #app { padding:18px; }

    .page-header {
        flex-direction:column;
    }

    .timeline-node.step {
        grid-template-columns:26px minmax(0,1fr);
        gap:10px;
    }

    .timeline-marker {
        min-width:26px;
    }

    .timeline-card-header {
        flex-direction:column;
        align-items:stretch;
        gap:10px;
    }

    .timeline-header-actions {
        width:100%;
        justify-content:flex-start;
        flex-wrap:wrap;
    }

    .timeline-duration {
        grid-template-columns:1fr;
        gap:10px;
        padding:12px 16px 14px;
    }

    .timeline-duration-value {
        justify-content:flex-start;
        order:3;
    }

    .timeline-duration-line {
        display:none;
    }

    .timeline-card .step-body {
        padding-left:16px;
        padding-right:16px;
    }

    .timeline-card .step-info {
        grid-template-columns:1fr;
    }

    .step-header {
        align-items:flex-start;
        flex-direction:column;
    }

    .step-meta {
        width:100%;
        justify-content:flex-start;
        flex-wrap:wrap;
    }

    .result-field {
        grid-template-columns:1fr;
    }

    .result-field-label {
        border-bottom:1px solid var(--border);
    }
}
"""
