REPORT_CSS = r''':root {
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
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); }
button, input { font: inherit; }
#app { max-width: 1440px; margin: auto; padding: 28px; }
.header { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:22px; }
.brand { font-size:12px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }
h1 { margin:6px 0; font-size:30px; }
h2 { margin:0; font-size:19px; }
h3 { margin:0 0 12px; font-size:15px; }
.muted, .meta { color:var(--muted); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.status { padding:8px 14px; border-radius:999px; font-weight:800; font-size:13px; }
.status-success, .status-completed { color:var(--success); background:#e7f5ed; }
.status-failed { color:var(--danger); background:#fdeaea; }
.status-cancelled, .status-skipped { color:var(--warning); background:#fff3df; }
.status-running { color:var(--info); background:#e8f2fb; }
.panel { background:var(--surface); border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); margin-bottom:18px; overflow:hidden; }
.panel-header { padding:17px 20px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; gap:12px; }
.panel-body { padding:20px; }
.alert { border-left:4px solid var(--danger); background:#fff7f7; padding:16px 18px; }
.alert-title { color:var(--danger); font-weight:800; margin-bottom:7px; }
.summary-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.metric { padding:16px; border:1px solid var(--border); border-radius:9px; background:#fff; }
.metric-label { color:var(--muted); font-size:12px; }
.metric-value { margin-top:5px; font-size:22px; font-weight:800; }
.controls { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
.search { flex:1; min-width:240px; padding:9px 12px; border:1px solid var(--border); border-radius:8px; }
.filter { border:1px solid var(--border); background:#fff; padding:8px 12px; border-radius:8px; cursor:pointer; }
.filter.active { background:#17202a; color:#fff; }
.step { border:1px solid var(--border); border-radius:10px; margin-bottom:12px; overflow:hidden; background:#fff; }
.step.hidden { display:none; }
.step-head { display:flex; justify-content:space-between; gap:15px; padding:15px 17px; align-items:center; }
.step-title { display:flex; gap:10px; align-items:center; }
.step-index { width:28px; height:28px; border-radius:50%; display:grid; place-items:center; background:#edf0f3; font-weight:800; font-size:12px; }
.step-name { font-weight:800; }
.step-meta { font-size:12px; color:var(--muted); margin-top:3px; }
.step-body { border-top:1px solid var(--border); padding:17px; }
.info-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:15px; }
.info-item { padding:11px 13px; background:#f7f8fa; border-radius:8px; }
.info-item label { display:block; color:var(--muted); font-size:11px; margin-bottom:3px; }
.message { padding:9px 11px; border-radius:7px; margin:6px 0; font-size:13px; border-left:3px solid var(--border); background:#fafafa; }
.message.WARNING { border-left-color:var(--warning); }
.message.ERROR, .message.CRITICAL { border-left-color:var(--danger); }
.message.INFO { border-left-color:var(--info); }
.level { font-size:10px; font-weight:800; margin-right:7px; }
.tree { border-left:2px solid #e5e8eb; margin-left:8px; padding-left:15px; }
.tree-row { display:flex; justify-content:space-between; gap:12px; padding:7px 0; font-size:13px; }
.tree-row .name { font-weight:650; }
.actions { display:flex; gap:8px; }
.action { border:1px solid var(--border); background:#fff; border-radius:7px; padding:7px 10px; cursor:pointer; font-size:12px; }
.result-button { font-weight:700; }
.chart { width:100%; overflow:auto; }
.bar-row { display:grid; grid-template-columns:220px 1fr 80px; align-items:center; gap:12px; margin:9px 0; font-size:12px; }
.bar { height:12px; background:#e9edf1; border-radius:6px; overflow:hidden; }
.bar > span { display:block; height:100%; background:#536878; border-radius:6px; }
.timeline-item { display:grid; grid-template-columns:170px 160px 1fr; gap:12px; padding:9px 0; border-bottom:1px solid #edf0f2; font-size:12px; }
.timeline-item:last-child { border-bottom:0; }
.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.45); display:none; align-items:center; justify-content:center; padding:25px; z-index:10; }
.modal-backdrop.open { display:flex; }
.modal { width:min(900px,100%); max-height:90vh; overflow:auto; background:#fff; border-radius:12px; box-shadow:0 15px 50px rgba(0,0,0,.25); }
.modal-head { padding:16px 20px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
.modal-body { padding:20px; }
.close { border:0; background:transparent; font-size:24px; cursor:pointer; }
.kv { display:grid; grid-template-columns:minmax(130px, 220px) 1fr; border-bottom:1px solid #edf0f2; }
.kv:last-child { border-bottom:0; }
.kv-key, .kv-value { padding:9px 10px; }
.kv-key { font-weight:700; color:#46515b; background:#f7f8fa; }
.raw { margin-top:18px; }
.raw pre { max-height:280px; overflow:auto; background:#17202a; color:#e9eef2; padding:14px; border-radius:8px; font-size:12px; }
.empty { color:var(--muted); padding:12px 0; }
@media (max-width: 900px) {
    #app { padding:16px; }
    .summary-grid { grid-template-columns:repeat(2,1fr); }
    .info-grid { grid-template-columns:1fr; }
    .timeline-item { grid-template-columns:1fr; gap:3px; }
}
@media (max-width: 600px) {
    .header { flex-direction:column; }
    .summary-grid { grid-template-columns:1fr 1fr; }
}
'''
