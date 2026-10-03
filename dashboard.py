"""Live web dashboard for fileSorter — Flask app with controls, charts, and settings."""

import logging
import subprocess
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

import config
import db
from main import DailyLogHandler
from sorter import (sweep, undo, undo_selected, is_temp_file, is_ignored,
                     get_client, get_regex_category, get_category)

LOG_DIR = Path(__file__).parent / "logs"
log = logging.getLogger("fileSorter")

app = Flask(__name__)

TASK_NAME = "FileSorter-Watch"


def _tray_available() -> bool:
    try:
        import tray
        return True
    except ImportError:
        return False


def _is_task_running() -> bool:
    if _tray_available():
        import tray
        return tray.is_watching()
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"(Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop).State"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "Running"
    except Exception:
        return False


def _start_task():
    if _tray_available():
        import tray
        tray._start_watcher()
        return
    subprocess.run(
        ["powershell", "-Command", f"Start-ScheduledTask -TaskName '{TASK_NAME}'"],
        capture_output=True, timeout=5,
    )


def _stop_task():
    if _tray_available():
        import tray
        tray._stop_watcher()
        return
    subprocess.run(
        ["powershell", "-Command", f"Stop-ScheduledTask -TaskName '{TASK_NAME}'"],
        capture_output=True, timeout=5,
    )
    subprocess.run(
        ["powershell", "-Command",
         "Get-Process -Name pythonw -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True, timeout=5,
    )


# --- Shared CSS ---

SHARED_CSS = r"""
:root {
    --bg: #000000; --card: #111111; --text: #e4e4e7;
    --muted: #a1a1aa; --border: #27272a;
    --primary: #2563eb; --success: #16a34a;
    --warning: #ea580c; --danger: #dc2626; --info: #0891b2;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: Segoe UI, system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 24px; max-width: 1200px; margin: 0 auto;
}
h1 { font-size: 24px; margin-bottom: 4px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
.header-left h1 { margin-bottom: 2px; }
.subtitle { color: var(--muted); font-size: 13px; }
.controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.btn {
    padding: 8px 18px; border: 1px solid transparent; border-radius: 8px; cursor: pointer;
    font-family: inherit; font-size: 13px; font-weight: 600; color: white;
    display: inline-flex; align-items: center; justify-content: center;
    line-height: 1; text-decoration: none; transition: opacity 0.2s;
}
.btn:hover { opacity: 0.85; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--primary); }
.btn-success { background: var(--success); }
.btn-warning { background: var(--warning); }
.btn-danger { background: var(--danger); }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-outline {
    background: transparent; border: 1px solid var(--border); color: var(--text);
}
.btn-outline:hover { border-color: var(--primary); color: var(--primary); }
.chart-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; margin-bottom: 16px;
}
.chart-card h3 { font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.section-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
}
.section-header h3 { margin-bottom: 0; }
table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
.history-table-wrap { height: 540px; overflow-y: auto; }
th {
    text-align: left; color: var(--muted); font-weight: 600;
    padding: 6px 10px; border-bottom: 2px solid var(--border);
    position: sticky; top: 0; background: var(--card); z-index: 1;
}
td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
tr:hover { background: var(--bg); }
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 600; background: #1e293b; color: #93c5fd;
}
.toast {
    position: fixed; bottom: 24px; right: 24px; padding: 12px 20px;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; font-size: 13px; font-weight: 600;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    transform: translateY(80px); opacity: 0; transition: all 0.3s;
    z-index: 100;
}
.toast.show { transform: translateY(0); opacity: 1; }
.footer { text-align: center; color: var(--muted); font-size: 11px; margin-top: 20px; }
a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }
"""


# --- API routes ---

@app.route("/")
def index():
    return render_template_string(DASHBOARD_TEMPLATE, css=SHARED_CSS)


@app.route("/settings")
def settings_page():
    return render_template_string(SETTINGS_TEMPLATE, css=SHARED_CSS)


@app.route("/api/stats")
def api_stats():
    date_filter = request.args.get("date") or None
    category_filter = request.args.get("category") or None
    data = db.get_stats(date_filter, category_filter)
    data["watching"] = _is_task_running()
    return jsonify(data)


@app.route("/api/history")
def api_history():
    date_filter = request.args.get("date") or None
    category_filter = request.args.get("category") or None
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    result = db.get_history(date_filter, page, per_page, category_filter)
    for item in result["items"]:
        dest = Path(item["dest"])
        item["file"] = Path(item["src"]).name
        try:
            item["dest_display"] = str(dest.relative_to(config.DOWNLOADS_FOLDER))
        except ValueError:
            item["dest_display"] = str(dest)
        item["exists"] = dest.exists()
    return jsonify(result)


@app.route("/api/sweep", methods=["POST"])
def api_sweep():
    count = sweep(config.DOWNLOADS_FOLDER)
    return jsonify({"ok": True, "count": count})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    undone = undo(1)
    return jsonify({"ok": True, "undone": undone})


@app.route("/api/undo-all", methods=["POST"])
def api_undo_all():
    pending = db.get_pending_undos()
    undone = undo(len(pending))
    return jsonify({"ok": True, "undone": undone})


@app.route("/api/undo-selected", methods=["POST"])
def api_undo_selected():
    ids = request.json.get("ids", [])
    undone = undo_selected(ids)
    return jsonify({"ok": True, "undone": undone})


@app.route("/api/timeline")
def api_timeline():
    category_filter = request.args.get("category") or None
    rows = db.get_timeline(category_filter)
    return jsonify(rows)


@app.route("/api/undo-range", methods=["POST"])
def api_undo_range():
    start = request.json.get("start")
    end = request.json.get("end")
    if not start or not end:
        return jsonify({"ok": False, "error": "start and end required"}), 400
    ids = db.get_moves_in_range(start, end)
    undone = undo_selected(ids)
    return jsonify({"ok": True, "undone": undone, "total": len(ids)})


@app.route("/api/watcher", methods=["POST"])
def api_watcher():
    if _is_task_running():
        _stop_task()
        return jsonify({"ok": True, "watching": False})
    _start_task()
    return jsonify({"ok": True, "watching": _is_task_running()})


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify({
        "downloads_folder": str(config.DOWNLOADS_FOLDER),
        "debounce_seconds": config.DEBOUNCE_SECONDS,
        "categories": {k: sorted(v) for k, v in config.CATEGORIES.items()},
        "clients": config.CLIENTS,
        "client_subcategories": {
            k: {"keywords": v["keywords"], "extensions": sorted(v["extensions"])}
            for k, v in config.CLIENT_SUBCATEGORIES.items()
        },
        "ignore_list": config.IGNORE_LIST,
        "regex_rules": config.REGEX_RULES,
        "notifications_enabled": config.NOTIFICATIONS_ENABLED,
        "watched_folders": config.WATCHED_FOLDERS,
    })


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.json
    for key in ("categories", "clients", "client_subcategories",
                "ignore_list", "regex_rules", "downloads_folder",
                "debounce_seconds", "notifications_enabled", "watched_folders"):
        if key in data:
            db.save_setting(key, data[key])
    config.load_overrides()
    return jsonify({"ok": True})


@app.route("/api/settings/reset", methods=["POST"])
def api_reset_settings():
    key = request.json.get("key") if request.json else None
    if key:
        db.delete_setting(key)
    else:
        for k in ("categories", "clients", "client_subcategories",
                   "ignore_list", "regex_rules", "downloads_folder",
                   "debounce_seconds", "notifications_enabled", "watched_folders"):
            db.delete_setting(k)
    config.load_overrides()
    return jsonify({"ok": True})


@app.route("/api/test-sort", methods=["POST"])
def api_test_sort():
    filename = (request.json or {}).get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    path = Path(filename)
    steps = []
    result = {"filename": filename, "steps": steps}

    if is_temp_file(path):
        steps.append({"step": 1, "name": "Temp File", "matched": True,
                       "detail": f"Extension '{path.suffix}' is a temp file"})
        result["outcome"] = "skip"
        result["reason"] = "Temp file — skipped"
        return jsonify(result)
    steps.append({"step": 1, "name": "Temp File", "matched": False})

    if path.name.startswith("."):
        steps.append({"step": 2, "name": "Dotfile", "matched": True,
                       "detail": "Filename starts with '.'"})
        result["outcome"] = "skip"
        result["reason"] = "Dotfile — skipped"
        return jsonify(result)
    steps.append({"step": 2, "name": "Dotfile", "matched": False})

    if is_ignored(path):
        steps.append({"step": 3, "name": "Ignore List", "matched": True,
                       "detail": f"'{path.name}' matches an ignore pattern"})
        result["outcome"] = "skip"
        result["reason"] = "Ignore list — skipped"
        return jsonify(result)
    steps.append({"step": 3, "name": "Ignore List", "matched": False})

    client = get_client(path)
    if client:
        subcat = None
        subcat_reason = ""
        name_lower = path.stem.lower()
        for keyword, sc in config.CLIENT_KEYWORD_MAP.items():
            if keyword in name_lower:
                subcat = sc
                subcat_reason = f"keyword '{keyword}'"
                break
        if not subcat:
            subcat = config.CLIENT_EXTENSION_MAP.get(path.suffix.lower())
            if subcat:
                subcat_reason = f"extension '{path.suffix}'"
        dest = f"{client}\\{subcat}" if subcat else client
        detail = f"Client '{client}'"
        if subcat:
            detail += f" → {subcat} (matched by {subcat_reason})"
        else:
            detail += " → client root (no sub-category match)"
        steps.append({"step": 4, "name": "Client Match", "matched": True,
                       "detail": detail})
        result["outcome"] = "sort"
        result["reason"] = f"Client match — sorted to {dest}"
        result["destination"] = dest
        return jsonify(result)
    steps.append({"step": 4, "name": "Client Match", "matched": False})

    regex_cat = get_regex_category(path)
    if regex_cat:
        steps.append({"step": 5, "name": "Regex Rules", "matched": True,
                       "detail": f"Matched regex rule → '{regex_cat}'"})
        result["outcome"] = "sort"
        result["reason"] = f"Regex match — sorted to {regex_cat}"
        result["destination"] = regex_cat
        return jsonify(result)
    steps.append({"step": 5, "name": "Regex Rules", "matched": False})

    cat = get_category(path)
    if cat:
        steps.append({"step": 6, "name": "Extension", "matched": True,
                       "detail": f"'{path.suffix}' → {cat}"})
        result["outcome"] = "sort"
        result["reason"] = f"Extension match — sorted to {cat}"
        result["destination"] = cat
        return jsonify(result)
    steps.append({"step": 6, "name": "Extension", "matched": False})

    steps.append({"step": 7, "name": "Unknown", "matched": True,
                   "detail": f"No rule matches '{path.suffix or '(no extension)'}'"})
    result["outcome"] = "skip"
    result["reason"] = "Unknown extension — left in place"
    return jsonify(result)


# --- Dashboard template ---

DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>fileSorter Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
{{ css }}
.stats {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 20px;
}
.stat-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; text-align: center;
}
.stat-value { font-size: 28px; font-weight: 700; }
.stat-value.primary { color: var(--primary); }
.stat-value.success { color: var(--success); }
.stat-value.warning { color: var(--warning); }
.stat-value.info { color: var(--info); }
.stat-label { color: var(--muted); font-size: 12px; margin-top: 2px; }
.charts {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 12px; margin-bottom: 20px;
}
@media (max-width: 768px) { .charts { grid-template-columns: 1fr; } }
.full-width { grid-column: 1 / -1; }
.date-picker {
    padding: 5px 10px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--card); color: var(--text); font-size: 13px; cursor: pointer;
}
.status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    margin-right: 6px; vertical-align: middle;
}
.status-dot.on { background: var(--success); }
.status-dot.off { background: var(--muted); }
input[type="checkbox"] { cursor: pointer; accent-color: var(--primary); }
.row-gone { opacity: 0.45; }
.undo-bar {
    display: none; align-items: center; gap: 10px; padding: 8px 0;
    font-size: 13px;
}
.undo-bar.visible { display: flex; }
.selected-count { font-weight: 600; color: var(--primary); }
.timeline-controls {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    margin-top: 10px; font-size: 13px;
}
.timeline-controls input[type="datetime-local"] {
    padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--card); color: var(--text); font-size: 12px;
}
.timeline-controls .range-count {
    font-weight: 600; color: var(--primary); min-width: 80px;
}
.timeline-hint {
    font-size: 11px; color: var(--muted); margin-top: 4px;
}
.pagination {
    display: flex; justify-content: center; align-items: center;
    gap: 4px; padding: 12px 0 4px; font-size: 13px;
}
.pagination button {
    padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--card); color: var(--text); cursor: pointer; font-size: 12px;
}
.pagination button:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.pagination button.active { background: var(--primary); color: white; border-color: var(--primary); }
.pagination .page-info { color: var(--muted); font-size: 12px; margin: 0 8px; }
.per-page-select {
    padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--card); color: var(--text); font-size: 12px; cursor: pointer;
    margin-left: 8px;
}
</style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <h1>fileSorter Dashboard</h1>
        <span class="subtitle" id="statusText">Loading...</span>
    </div>
    <div class="controls">
        <button class="btn btn-primary" id="btnWatcher" onclick="toggleWatcher()">Start Watcher</button>
        <button class="btn btn-success" onclick="doSweep()">Sweep Now</button>
        <a href="/settings" class="btn" title="Settings" style="font-size:16px;padding:6px 10px;background:var(--card);color:var(--text)">&#9881;</a>
    </div>
</div>

<div class="stats">
    <div class="stat-card"><div class="stat-value primary" id="sMoved">-</div><div class="stat-label">Files Sorted</div></div>
    <div class="stat-card"><div class="stat-value warning" id="sUndone">-</div><div class="stat-label">Files Undone</div></div>
    <div class="stat-card"><div class="stat-value success" id="sSweeps">-</div><div class="stat-label">Sweeps Run</div></div>
    <div class="stat-card"><div class="stat-value info" id="sDays">-</div><div class="stat-label">Days Active</div></div>
</div>

<div class="charts">
    <div class="chart-card">
        <div class="section-header">
            <h3>Files by Category</h3>
            <div style="display:flex;gap:8px;align-items:center">
                <select id="categoryFilter" class="date-picker" onchange="onCategoryChange()">
                    <option value="">All categories</option>
                </select>
                <select id="dateFilter" class="date-picker" onchange="onDateChange()">
                    <option value="">All dates</option>
                </select>
            </div>
        </div>
        <canvas id="catChart"></canvas>
    </div>
    <div class="chart-card"><h3>Activity by Hour</h3><canvas id="hourChart"></canvas></div>
    <div class="chart-card full-width"><h3>Files Sorted per Day</h3><canvas id="dailyChart" height="80"></canvas></div>
</div>

<div class="chart-card">
    <h3>Undo Timeline</h3>
    <canvas id="timelineChart" height="100"></canvas>
    <div class="timeline-controls">
        <label>From <input type="datetime-local" id="tlFrom" onchange="updateTimelineCount()"></label>
        <label>To <input type="datetime-local" id="tlTo" onchange="updateTimelineCount()"></label>
        <span class="range-count" id="tlCount"></span>
        <button class="btn btn-warning btn-sm" id="tlUndoBtn" onclick="undoRange()" disabled>Undo Range</button>
    </div>
    <p class="timeline-hint">Click and drag on the chart to select a time range, or use the date inputs above.</p>
</div>

<div class="chart-card">
    <div class="section-header">
        <h3>Move History</h3>
        <input type="text" id="historySearch" placeholder="Search files..." oninput="filterHistory()"
            style="padding:5px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:13px;width:220px">
    </div>
    <div class="undo-bar" id="undoBar">
        <input type="checkbox" id="selectAll" onchange="toggleSelectAll()">
        <span><span class="selected-count" id="selectedCount">0</span> selected</span>
        <button class="btn btn-warning btn-sm" onclick="undoSelected()">Undo Selected</button>
    </div>
    <div class="history-table-wrap">
    <table>
        <thead><tr><th style="width:30px"></th><th style="width:140px">Time</th><th>File</th><th>Moved To</th><th style="width:60px">Status</th></tr></thead>
        <tbody id="historyBody"></tbody>
    </table>
    </div>
    <div class="pagination" id="pagination"></div>
</div>

<div class="toast" id="toast"></div>
<p class="footer">fileSorter &middot; Auto-refreshes every 10s</p>

<script>
const COLORS = ['#2563eb','#16a34a','#ea580c','#8b5cf6','#ec4899','#0891b2','#d97706','#dc2626','#059669','#6366f1'];
const categoryColorMap = {};
function getCategoryColors(labels) {
    labels.forEach(l => { if (!(l in categoryColorMap)) categoryColorMap[l] = COLORS[Object.keys(categoryColorMap).length % COLORS.length]; });
    return labels.map(l => categoryColorMap[l]);
}
let catChart = null, hourChart = null, dailyChart = null, timelineChart = null;
let timelineData = [];
let watching = false;
let currentDate = '';
let currentCategory = '';
let historyItems = [];
let currentPage = 1;
let totalPages = 1;
let totalItems = 0;
let perPage = 50;

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
}
async function apiPost(url, body) {
    const opts = { method:'POST', headers:{'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    return (await fetch(url, opts)).json();
}
async function doSweep() {
    showToast('Sweeping...');
    const d = await apiPost('/api/sweep');
    showToast('Sweep done: ' + d.count + ' file(s) sorted'); refresh();
}
async function toggleWatcher() {
    const btn = document.getElementById('btnWatcher');
    btn.disabled = true;
    showToast(watching ? 'Stopping watcher...' : 'Starting watcher...');
    const d = await apiPost('/api/watcher');
    watching = d.watching; updateWatcherBtn(); btn.disabled = false;
    showToast(watching ? 'Watcher started' : 'Watcher stopped');
}
function updateWatcherBtn() {
    const btn = document.getElementById('btnWatcher');
    btn.textContent = watching ? 'Stop Watcher' : 'Start Watcher';
    btn.className = watching ? 'btn btn-danger' : 'btn btn-primary';
    document.getElementById('statusText').innerHTML =
        '<span class="status-dot '+(watching?'on':'off')+'"></span>'+(watching?'Watcher running':'Watcher stopped');
}
function truncate(s,n){return s.length>n?s.slice(0,n)+'...':s;}
function escapeHtml(s){const el=document.createElement('div');el.textContent=s;return el.innerHTML;}
function onDateChange(){currentDate=document.getElementById('dateFilter').value;currentPage=1;refresh();}
function onCategoryChange(){currentCategory=document.getElementById('categoryFilter').value;currentPage=1;refresh();}
function getCheckedIds(){return Array.from(document.querySelectorAll('.row-cb:checked')).map(cb=>parseInt(cb.dataset.id));}
function updateUndoBar(){
    const n=getCheckedIds().length;
    document.getElementById('undoBar').className=n?'undo-bar visible':'undo-bar';
    document.getElementById('selectedCount').textContent=n;
}
function toggleSelectAll(){
    const all=document.getElementById('selectAll').checked;
    document.querySelectorAll('.row-cb:not(:disabled)').forEach(cb=>cb.checked=all);
    updateUndoBar();
}
async function undoSelected(){
    const ids=getCheckedIds(); if(!ids.length)return;
    showToast('Undoing '+ids.length+' file(s)...');
    const d=await apiPost('/api/undo-selected',{ids});
    showToast(d.undone?'Undone '+d.undone+' file(s)':'Nothing to undo');
    document.getElementById('selectAll').checked=false; refresh();
}
function initCharts(){
    Chart.defaults.color='#a1a1aa';
    Chart.defaults.borderColor='#27272a';
    const o={animation:false};
    catChart=new Chart(document.getElementById('catChart'),{type:'doughnut',data:{labels:[],datasets:[{data:[],backgroundColor:[]}]},options:{...o,responsive:true,plugins:{legend:{position:'bottom',labels:{boxWidth:12,padding:8,font:{size:11}}}}}});
    hourChart=new Chart(document.getElementById('hourChart'),{type:'bar',data:{labels:Array.from({length:24},(_,i)=>String(i).padStart(2,'0')+':00'),datasets:[{data:new Array(24).fill(0),backgroundColor:'#2563eb88',borderRadius:4}]},options:{...o,responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}});
    dailyChart=new Chart(document.getElementById('dailyChart'),{type:'line',data:{labels:[],datasets:[{data:[],borderColor:'#2563eb',backgroundColor:'#2563eb22',fill:true,tension:0.3,pointRadius:4}]},options:{...o,responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}});
    timelineChart=new Chart(document.getElementById('timelineChart'),{type:'bar',data:{labels:[],datasets:[{data:[],backgroundColor:[]}]},options:{...o,responsive:true,plugins:{legend:{display:false},tooltip:{callbacks:{title:function(items){return items[0]?.label||'';},label:function(ctx){return ctx.raw+' file(s)';}}}},scales:{x:{grid:{display:false},ticks:{maxRotation:45,font:{size:10}}},y:{beginAtZero:true,ticks:{stepSize:1}}},onClick:function(evt,el){if(el.length){const idx=el[0].index;const label=timelineChart.data.labels[idx];onTimelineClick(label);}}}});
}
async function refresh(){
    const params=new URLSearchParams();
    if(currentDate)params.set('date',currentDate);
    if(currentCategory)params.set('category',currentCategory);
    const q=params.toString()?'?'+params.toString():'';
    const hParams=new URLSearchParams(params);
    hParams.set('page',currentPage);hParams.set('per_page',perPage);
    const [sr,hr]=await Promise.all([fetch('/api/stats'+q),fetch('/api/history?'+hParams.toString())]);
    const d=await sr.json(), h=await hr.json();
    watching=d.watching; updateWatcherBtn();
    document.getElementById('sMoved').textContent=d.total_moved;
    document.getElementById('sUndone').textContent=d.total_undone;
    document.getElementById('sSweeps').textContent=d.total_sweeps;
    document.getElementById('sDays').textContent=d.days_active;
    const sel=document.getElementById('dateFilter'), prev=sel.value;
    sel.innerHTML='<option value="">All dates</option>'+(d.available_dates||[]).map(dt=>'<option value="'+dt+'"'+(dt===prev?' selected':'')+'>'+dt+'</option>').join('');
    const catSel=document.getElementById('categoryFilter'), prevCat=catSel.value;
    const acats=d.available_categories||[];
    let catOpts='<option value="">All categories</option>';
    const catGroups={};
    acats.forEach(c=>{const p=c.split('/')[0];if(!catGroups[p])catGroups[p]=[];catGroups[p].push(c);});
    for(const [p,subs] of Object.entries(catGroups)){
        if(subs.length===1&&subs[0]===p){catOpts+='<option value="'+escapeHtml(p)+'"'+(p===prevCat?' selected':'')+'>'+escapeHtml(p)+'</option>';}
        else{catOpts+='<optgroup label="'+escapeHtml(p)+'">';subs.forEach(c=>{const label=c.includes('/')?'  '+c.split('/').slice(1).join('/'):c;catOpts+='<option value="'+escapeHtml(c)+'"'+(c===prevCat?' selected':'')+'>'+escapeHtml(label)+'</option>';});catOpts+='</optgroup>';}
    }
    catSel.innerHTML=catOpts;
    const parentCats = (d.available_categories||[]).map(c=>c.split('/')[0]).filter((v,i,a)=>a.indexOf(v)===i);
    getCategoryColors(parentCats);
    const grouped={};
    for(const [cat,cnt] of Object.entries(d.categories)){
        const parent=cat.split('/')[0];
        grouped[parent]=(grouped[parent]||0)+cnt;
    }
    const catLabels=Object.keys(grouped);
    catChart.data.labels=catLabels; catChart.data.datasets[0].data=Object.values(grouped);
    catChart.data.datasets[0].backgroundColor=getCategoryColors(catLabels); catChart.update();
    hourChart.data.datasets[0].data=Array.from({length:24},(_,i)=>d.hourly[i]||0); hourChart.update();
    dailyChart.data.labels=Object.keys(d.daily); dailyChart.data.datasets[0].data=Object.values(d.daily); dailyChart.update();
    historyItems=h.items;
    totalPages=h.pages;
    totalItems=h.total;
    renderHistory();
    renderPagination();
    refreshTimeline();
}
async function refreshTimeline(){
    const catParam=currentCategory?'?category='+encodeURIComponent(currentCategory):'';
    const tr=await fetch('/api/timeline'+catParam);
    timelineData=await tr.json();
    const buckets={};
    timelineData.forEach(m=>{
        const h=m.timestamp.slice(0,13);
        buckets[h]=(buckets[h]||0)+1;
    });
    const labels=Object.keys(buckets).sort();
    const data=labels.map(l=>buckets[l]);
    const fromEl=document.getElementById('tlFrom'),toEl=document.getElementById('tlTo');
    const selFrom=fromEl.value?fromEl.value.replace('T',' '):'';
    const selTo=toEl.value?toEl.value.replace('T',' '):'';
    const colors=labels.map(l=>{
        const hStart=l+':00:00';
        const hEnd=l+':59:59';
        if(selFrom&&selTo&&hStart>=selFrom&&hEnd<=selTo+':59') return '#d97706';
        return '#2563eb88';
    });
    timelineChart.data.labels=labels.map(l=>{const d=new Date(l+':00:00');return d.toLocaleDateString('en',{month:'short',day:'numeric'})+' '+d.toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit',hour12:false});});
    timelineChart.data.datasets[0].data=data;
    timelineChart.data.datasets[0].backgroundColor=colors;
    timelineChart.data._rawLabels=labels;
    timelineChart.update();
}

function onTimelineClick(label){
    const idx=timelineChart.data.labels.indexOf(label);
    const rawLabels=timelineChart.data._rawLabels;
    if(idx<0||!rawLabels) return;
    const raw=rawLabels[idx];
    const fromEl=document.getElementById('tlFrom'),toEl=document.getElementById('tlTo');
    if(!fromEl.value||toEl.value){
        fromEl.value=raw.replace(' ','T')+':00';
        toEl.value='';
    } else {
        const clickVal=raw.replace(' ','T')+':59';
        if(clickVal<fromEl.value){
            toEl.value=fromEl.value.slice(0,16);
            fromEl.value=raw.replace(' ','T')+':00';
        } else {
            toEl.value=clickVal;
        }
    }
    updateTimelineCount();
}

function updateTimelineCount(){
    const fromEl=document.getElementById('tlFrom'),toEl=document.getElementById('tlTo');
    const btn=document.getElementById('tlUndoBtn');
    const countEl=document.getElementById('tlCount');
    if(!fromEl.value||!toEl.value){
        countEl.textContent='';
        btn.disabled=true;
        refreshTimeline();
        return;
    }
    const start=fromEl.value.replace('T',' ');
    const end=toEl.value.replace('T',' ');
    const count=timelineData.filter(m=>m.timestamp>=start&&m.timestamp<=end+':59').length;
    countEl.textContent=count+' file(s) in range';
    btn.disabled=count===0;
    refreshTimeline();
}

async function undoRange(){
    const fromEl=document.getElementById('tlFrom'),toEl=document.getElementById('tlTo');
    if(!fromEl.value||!toEl.value) return;
    const start=fromEl.value.replace('T',' ')+':00';
    const end=toEl.value.replace('T',' ')+':59';
    const count=timelineData.filter(m=>m.timestamp>=start&&m.timestamp<=end).length;
    if(!confirm('Undo '+count+' file(s) from '+fromEl.value+' to '+toEl.value+'?')) return;
    showToast('Undoing '+count+' file(s)...');
    const d=await apiPost('/api/undo-range',{start,end});
    showToast(d.undone?'Undone '+d.undone+' file(s)':'Nothing to undo');
    fromEl.value='';toEl.value='';
    document.getElementById('tlCount').textContent='';
    document.getElementById('tlUndoBtn').disabled=true;
    refresh();
}

function renderHistory(){
    const q=(document.getElementById('historySearch').value||'').toLowerCase();
    const filtered=q?historyItems.filter(i=>i.file.toLowerCase().includes(q)||i.dest_display.toLowerCase().includes(q)):historyItems;
    const tbody=document.getElementById('historyBody');
    tbody.innerHTML=filtered.map(item=>{
        const gone=!item.exists;
        return '<tr class="'+(gone?'row-gone':'')+'"><td><input type="checkbox" class="row-cb" data-id="'+item.id+'"'
            +(gone?' disabled title="File no longer exists"':'')+' onchange="updateUndoBar()"></td>'
            +'<td>'+escapeHtml(item.timestamp)+'</td>'
            +'<td title="'+escapeHtml(item.file)+'">'+escapeHtml(truncate(item.file,35))+'</td>'
            +'<td title="'+escapeHtml(item.dest_display)+'">'+escapeHtml(truncate(item.dest_display,35))+'</td>'
            +'<td>'+(gone?'<span style="color:var(--danger);font-size:11px">Missing</span>':'<span style="color:var(--success);font-size:11px">Exists</span>')+'</td></tr>';
    }).join('');
    updateUndoBar();
}
function filterHistory(){renderHistory();}
function goToPage(p){if(p<1||p>totalPages||p===currentPage)return;currentPage=p;refresh();}
function changePerPage(val){perPage=parseInt(val);currentPage=1;refresh();}
function renderPagination(){
    const el=document.getElementById('pagination');
    const sizes=[10,25,50,100];
    let html='';
    if(totalPages>1){
        html+='<button onclick="goToPage(1)"'+(currentPage===1?' disabled':'')+'>&#171;</button>';
        html+='<button onclick="goToPage(currentPage-1)"'+(currentPage===1?' disabled':'')+'>&#8249;</button>';
        const start=Math.max(1,currentPage-2),end=Math.min(totalPages,currentPage+2);
        if(start>1)html+='<span class="page-info">...</span>';
        for(let i=start;i<=end;i++){
            html+='<button onclick="goToPage('+i+')"'+(i===currentPage?' class="active"':'')+'>'+i+'</button>';
        }
        if(end<totalPages)html+='<span class="page-info">...</span>';
        html+='<button onclick="goToPage(currentPage+1)"'+(currentPage===totalPages?' disabled':'')+'>&#8250;</button>';
        html+='<button onclick="goToPage(totalPages)"'+(currentPage===totalPages?' disabled':'')+'>&#187;</button>';
    }
    html+='<span class="page-info">'+totalItems+' items</span>';
    html+='<select class="per-page-select" onchange="changePerPage(this.value)">';
    sizes.forEach(s=>{html+='<option value="'+s+'"'+(s===perPage?' selected':'')+'>'+s+' / page</option>';});
    html+='</select>';
    el.innerHTML=html;
}
initCharts(); refresh(); setInterval(refresh,10000);
</script>
</body>
</html>"""


# --- Settings template ---

SETTINGS_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>fileSorter Settings</title>
<style>
{{ css }}
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
.field input[type="text"], .field input[type="number"] {
    width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); color: var(--text); font-size: 13px;
}
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.tag {
    display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px;
    background: #1e293b; color: #93c5fd; border-radius: 10px; font-size: 11px; font-weight: 600;
}
.tag button {
    background: none; border: none; color: inherit; cursor: pointer; font-size: 13px;
    padding: 0 2px; opacity: 0.6;
}
.tag button:hover { opacity: 1; }
.add-row { display: flex; gap: 6px; margin-top: 6px; }
.add-row input {
    flex: 1; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--text); font-size: 12px;
}
.cat-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 10px;
}
.cat-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
}
.cat-header strong { font-size: 14px; }
.tree { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.tree-node { border-bottom: 1px solid var(--border); }
.tree-node:last-child { border-bottom: none; }
.tree-row {
    display: flex; align-items: center; gap: 8px; padding: 8px 12px;
    cursor: pointer; user-select: none; transition: background 0.15s;
}
.tree-row:hover { background: rgba(255,255,255,0.03); }
.tree-chevron {
    width: 16px; font-size: 10px; color: var(--muted); transition: transform 0.2s;
    flex-shrink: 0; text-align: center;
}
.tree-node.open > .tree-row .tree-chevron { transform: rotate(90deg); }
.tree-name { font-size: 13px; font-weight: 600; flex: 1; }
.tree-count {
    font-size: 11px; color: var(--muted); background: var(--border);
    padding: 1px 8px; border-radius: 10px;
}
.tree-remove {
    background: none; border: none; color: var(--danger); cursor: pointer;
    font-size: 15px; padding: 0 4px; opacity: 0.5; transition: opacity 0.15s;
}
.tree-remove:hover { opacity: 1; }
.tree-body {
    display: none; padding: 6px 12px 10px 36px;
    border-top: 1px solid var(--border); background: rgba(0,0,0,0.15);
}
.tree-node.open > .tree-body { display: block; }
.tree-group > .tree-body { padding-left: 0; }
.tree-group > .tree-body > .tree-sub { border-bottom: 1px solid var(--border); }
.tree-group > .tree-body > .tree-sub:last-child { border-bottom: none; }
.tree-sub > .tree-row { padding-left: 32px; }
.tree-sub > .tree-body { padding-left: 52px; }
.actions-bar {
    display: flex; gap: 8px; margin-top: 20px; padding-top: 16px;
    border-top: 1px solid var(--border);
}
.chart-card.step-skip { border-left: 3px solid #dc2626; }
.chart-card.step-match { border-left: 3px solid #16a34a; }
.chart-card.step-fallback { border-left: 3px solid #2563eb; }
.step-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; border-radius: 50%; font-size: 10px; font-weight: 700;
    margin-right: 6px; vertical-align: middle; flex-shrink: 0;
}
.step-badge.skip { background: #7f1d1d; color: #fca5a5; }
.step-badge.match { background: #14532d; color: #86efac; }
.step-badge.fallback { background: #1e3a5f; color: #93c5fd; }
.pipeline { display: flex; align-items: stretch; gap: 0; overflow-x: auto; padding: 4px 0; }
.pipe-step {
    display: flex; flex-direction: column; align-items: center; text-align: center;
    padding: 10px 14px; min-width: 110px; flex: 1; position: relative;
}
.pipe-step .pipe-num {
    width: 24px; height: 24px; border-radius: 50%; font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; margin-bottom: 6px;
    flex-shrink: 0;
}
.pipe-step .pipe-label { font-size: 11px; font-weight: 600; line-height: 1.3; }
.pipe-step .pipe-desc { font-size: 10px; color: var(--muted); margin-top: 3px; line-height: 1.3; }
.pipe-step.skip .pipe-num { background: #7f1d1d; color: #fca5a5; }
.pipe-step.skip { border-bottom: 2px solid #dc2626; }
.pipe-step.match .pipe-num { background: #14532d; color: #86efac; }
.pipe-step.match { border-bottom: 2px solid #16a34a; }
.pipe-step.fallback .pipe-num { background: #1e3a5f; color: #93c5fd; }
.pipe-step.fallback { border-bottom: 2px solid #2563eb; }
.pipe-step.end .pipe-num { background: var(--border); color: var(--muted); }
.pipe-step.end { border-bottom: 2px solid var(--border); }
.pipe-arrow {
    display: flex; align-items: center; color: var(--muted); font-size: 14px;
    padding: 0; flex-shrink: 0; margin-top: -10px;
}
.rule-tester { display: flex; gap: 8px; margin-bottom: 14px; }
.rule-tester input {
    flex: 1; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); color: var(--text); font-size: 14px;
}
.rule-tester input:focus { outline: none; border-color: var(--primary); }
.test-result {
    border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
    display: none;
}
.test-result.visible { display: block; }
.test-outcome {
    padding: 12px 16px; font-size: 14px; font-weight: 600;
    display: flex; align-items: center; gap: 10px;
}
.test-outcome.sort { background: #052e16; color: #86efac; }
.test-outcome.skip { background: #450a0a; color: #fca5a5; }
.test-dest { font-weight: 400; opacity: 0.85; }
.test-steps {
    display: flex; gap: 0; padding: 0; border-top: 1px solid var(--border);
}
.test-step {
    flex: 1; padding: 8px 6px; text-align: center; font-size: 11px;
    border-right: 1px solid var(--border); position: relative;
}
.test-step:last-child { border-right: none; }
.test-step .ts-num {
    width: 20px; height: 20px; border-radius: 50%; font-size: 10px; font-weight: 700;
    display: inline-flex; align-items: center; justify-content: center; margin-bottom: 3px;
}
.test-step .ts-label { display: block; font-weight: 600; color: var(--muted); }
.test-step.pass .ts-num { background: var(--border); color: var(--muted); }
.test-step.pass .ts-label { color: var(--muted); }
.test-step.hit-sort .ts-num { background: #14532d; color: #86efac; }
.test-step.hit-sort .ts-label { color: #86efac; }
.test-step.hit-sort { background: rgba(22,163,74,0.08); }
.test-step.hit-skip .ts-num { background: #7f1d1d; color: #fca5a5; }
.test-step.hit-skip .ts-label { color: #fca5a5; }
.test-step.hit-skip { background: rgba(220,38,38,0.08); }
.test-step .ts-detail {
    display: block; font-size: 10px; color: var(--muted); margin-top: 2px;
    font-weight: 400;
}
.cheatsheet { display: none; margin-top: 12px; }
.cheatsheet.open { display: block; }
.cheatsheet-toggle {
    background: none; border: none; color: var(--primary); cursor: pointer;
    font-size: 12px; font-weight: 600; padding: 0; display: inline-flex;
    align-items: center; gap: 4px;
}
.cheatsheet-toggle:hover { text-decoration: underline; }
.cheatsheet-toggle .chev { font-size: 9px; transition: transform 0.2s; }
.cheatsheet.open ~ .cheatsheet-toggle .chev,
.cheatsheet-toggle.open .chev { transform: rotate(90deg); }
.cs-table { margin-top: 8px; }
.cs-table th { font-size: 11px; padding: 6px 10px; text-align: left; }
.cs-table td { font-size: 12px; padding: 5px 10px; }
.cs-table code {
    background: #1e293b; padding: 2px 6px; border-radius: 4px;
    font-size: 11px; color: #93c5fd;
}
.cs-table .cs-desc { color: var(--muted); font-size: 11px; }
.cs-example {
    margin-top: 10px; padding: 10px 14px; background: var(--bg);
    border: 1px solid var(--border); border-radius: 8px; font-size: 12px;
}
.cs-example strong { font-size: 11px; color: var(--muted); display: block; margin-bottom: 6px; }
.cs-example div { margin-bottom: 4px; }
.cs-example code { background: #1e293b; padding: 2px 6px; border-radius: 4px; font-size: 11px; color: #93c5fd; }
.cs-example .cs-arrow { color: var(--muted); margin: 0 4px; }
.wf-card {
    background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 10px;
}
.wf-header {
    display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
}
.wf-header .wf-path { flex: 1; font-size: 13px; font-weight: 600; word-break: break-all; }
.wf-toggle { display: flex; align-items: center; gap: 6px; }
.wf-toggle label { font-size: 11px; color: var(--muted); cursor: pointer; }
.wf-rules { display: flex; flex-wrap: wrap; gap: 8px; }
.wf-rule {
    display: flex; align-items: center; gap: 5px; padding: 4px 10px;
    background: var(--card); border: 1px solid var(--border); border-radius: 6px;
    font-size: 11px;
}
.wf-rule input { width: auto; cursor: pointer; accent-color: var(--primary); }
.wf-rule label { cursor: pointer; color: var(--text); }
.wf-rule.disabled label { color: var(--muted); }
</style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <h1>Settings</h1>
        <span class="subtitle"><a href="/">Back to Dashboard</a></span>
    </div>
    <div class="controls">
        <button class="btn btn-primary" onclick="saveAll()">Save Settings</button>
        <button class="btn" onclick="exportSettings()" style="background:var(--card);color:var(--text)">Export</button>
        <button class="btn" onclick="document.getElementById('importFile').click()" style="background:var(--card);color:var(--text)">Import</button>
        <input type="file" id="importFile" accept=".json" style="display:none" onchange="importSettings(this)">
        <button class="btn btn-danger" onclick="resetAll()">Reset to Defaults</button>
    </div>
</div>

<!-- Sorting Pipeline -->
<div class="chart-card">
    <h3>Sorting Priority</h3>
    <p style="font-size:12px;color:var(--muted);margin:4px 0 12px">Files are evaluated in this order &mdash; first match wins.</p>
    <div class="pipeline">
        <div class="pipe-step skip">
            <span class="pipe-num">1</span>
            <span class="pipe-label">Temp File</span>
            <span class="pipe-desc">.crdownload, .part, .tmp</span>
        </div>
        <span class="pipe-arrow">&#9654;</span>
        <div class="pipe-step skip">
            <span class="pipe-num">2</span>
            <span class="pipe-label">Dotfile</span>
            <span class="pipe-desc">.hidden files</span>
        </div>
        <span class="pipe-arrow">&#9654;</span>
        <div class="pipe-step skip">
            <span class="pipe-num">3</span>
            <span class="pipe-label">Ignore List</span>
            <span class="pipe-desc">Glob patterns to skip</span>
        </div>
        <span class="pipe-arrow">&#9654;</span>
        <div class="pipe-step match">
            <span class="pipe-num">4</span>
            <span class="pipe-label">Client Match</span>
            <span class="pipe-desc">Keyword &#8594; client folder + sub-category</span>
        </div>
        <span class="pipe-arrow">&#9654;</span>
        <div class="pipe-step match">
            <span class="pipe-num">5</span>
            <span class="pipe-label">Regex Rules</span>
            <span class="pipe-desc">Pattern &#8594; custom folder</span>
        </div>
        <span class="pipe-arrow">&#9654;</span>
        <div class="pipe-step fallback">
            <span class="pipe-num">6</span>
            <span class="pipe-label">Extension</span>
            <span class="pipe-desc">Category by file type</span>
        </div>
        <span class="pipe-arrow">&#9654;</span>
        <div class="pipe-step end">
            <span class="pipe-num">7</span>
            <span class="pipe-label">Unknown</span>
            <span class="pipe-desc">Left in place</span>
        </div>
    </div>
</div>

<!-- Rule Tester -->
<div class="chart-card">
    <h3>Rule Tester</h3>
    <p style="font-size:12px;color:var(--muted);margin:4px 0 10px">Type a filename to see which rule matches and where it would be sorted.</p>
    <div class="rule-tester">
        <input type="text" id="testFilename" placeholder="e.g. AKSS_proposal.pdf, screenshot_2026.png, .gitignore" onkeydown="if(event.key==='Enter')testSort()">
        <button class="btn btn-primary" onclick="testSort()">Test</button>
    </div>
    <div class="test-result" id="testResult"></div>
</div>

<!-- General -->
<div class="chart-card">
    <h3>General</h3>
    <div class="field">
        <label>Downloads Folder</label>
        <input type="text" id="cfgFolder">
    </div>
    <div class="field">
        <label>Debounce Delay (seconds)</label>
        <input type="number" id="cfgDebounce" min="1" max="30">
    </div>
    <div class="field" style="display:flex;align-items:center;gap:8px;margin-top:4px">
        <input type="checkbox" id="cfgNotify" style="width:auto">
        <label for="cfgNotify" style="display:inline;margin:0;cursor:pointer">Enable desktop notifications</label>
    </div>
</div>

<!-- Watched Folders -->
<div class="chart-card">
    <h3>Watched Folders</h3>
    <p style="font-size:12px;color:var(--muted);margin:4px 0 10px">Folders that the watcher monitors. Toggle rules per folder to control which sorting steps apply.</p>
    <div id="watchedFolders"></div>
    <div class="add-row" style="margin-top:10px">
        <input type="text" id="newWatchFolder" placeholder="Folder path (e.g. C:\Users\you\Desktop)" onkeydown="if(event.key==='Enter')addWatchedFolder()">
        <button class="btn btn-sm btn-primary" onclick="addWatchedFolder()">Add</button>
    </div>
</div>

<!-- Step 3: Ignore List -->
<div class="chart-card step-skip">
    <h3><span class="step-badge skip">3</span>Ignore List</h3>
    <div class="tag-list" id="ignoreList"></div>
    <div class="add-row">
        <input type="text" id="ignoreInput" placeholder="Pattern (e.g. *.bak, desktop.ini)" onkeydown="if(event.key==='Enter')addIgnore()">
        <button class="btn btn-sm btn-primary" onclick="addIgnore()">Add</button>
    </div>
</div>

<!-- Step 4: Clients -->
<div class="chart-card step-match">
    <div class="section-header">
        <h3><span class="step-badge match">4</span>Clients</h3>
    </div>
    <div id="clientContainer"></div>
    <div class="add-row" style="margin-top:10px">
        <input type="text" id="newClientInput" placeholder="New client name (e.g. ACME)" onkeydown="if(event.key==='Enter')addClient()">
        <button class="btn btn-sm btn-primary" onclick="addClient()">Add</button>
    </div>
</div>

<!-- Step 4: Client Sub-categories -->
<div class="chart-card step-match">
    <div class="section-header">
        <h3><span class="step-badge match">4</span>Client Sub-categories</h3>
    </div>
    <div id="subcatContainer"></div>
    <div class="add-row" style="margin-top:10px">
        <input type="text" id="newSubcatInput" placeholder="Sub-category name (e.g. 04. Design or 01. Commercial/Tenders)" onkeydown="if(event.key==='Enter')addSubcat()">
        <button class="btn btn-sm btn-primary" onclick="addSubcat()">Add</button>
    </div>
</div>

<!-- Step 5: Regex Rules -->
<div class="chart-card step-match">
    <div class="section-header">
        <h3><span class="step-badge match">5</span>Regex Rules</h3>
    </div>
    <table id="regexTable">
        <thead><tr><th>Pattern</th><th>Folder</th><th style="width:40px"></th></tr></thead>
        <tbody id="regexBody"></tbody>
    </table>
    <div class="add-row" style="margin-bottom:10px">
        <input type="text" id="regexPatternInput" placeholder="Pattern (e.g. ^INV-\d+)" onkeydown="if(event.key==='Enter')document.getElementById('regexFolderInput').focus()">
        <input type="text" id="regexFolderInput" placeholder="Folder (e.g. Invoices)" onkeydown="if(event.key==='Enter')addRegex()">
        <button class="btn btn-sm btn-primary" onclick="addRegex()">Add</button>
    </div>
    <button class="cheatsheet-toggle" id="csToggle" onclick="document.getElementById('csSheet').classList.toggle('open');this.classList.toggle('open')">
        <span class="chev">&#9654;</span> Regex Cheat Sheet
    </button>
    <div class="cheatsheet" id="csSheet">
        <table class="cs-table" style="width:100%">
            <thead><tr><th>Symbol</th><th>Meaning</th><th>Example</th></tr></thead>
            <tbody>
                <tr><td><code>abc</code></td><td>Matches the exact text "abc"</td><td class="cs-desc"><code>invoice</code> matches any filename containing "invoice"</td></tr>
                <tr><td><code>^</code></td><td>Start of filename</td><td class="cs-desc"><code>^INV</code> matches files starting with "INV"</td></tr>
                <tr><td><code>$</code></td><td>End of filename</td><td class="cs-desc"><code>report$</code> matches files ending with "report"</td></tr>
                <tr><td><code>.</code></td><td>Any single character</td><td class="cs-desc"><code>file.txt</code> matches "file1txt", "fileAtxt", etc.</td></tr>
                <tr><td><code>\.</code></td><td>A literal dot</td><td class="cs-desc"><code>file\.txt</code> matches exactly "file.txt"</td></tr>
                <tr><td><code>\d</code></td><td>Any digit (0-9)</td><td class="cs-desc"><code>INV-\d\d\d</code> matches "INV-001", "INV-999"</td></tr>
                <tr><td><code>\d+</code></td><td>One or more digits</td><td class="cs-desc"><code>INV-\d+</code> matches "INV-1", "INV-12345"</td></tr>
                <tr><td><code>.*</code></td><td>Any characters (zero or more)</td><td class="cs-desc"><code>^report.*pdf</code> matches "report_2026.pdf"</td></tr>
                <tr><td><code>[abc]</code></td><td>Any one of a, b, or c</td><td class="cs-desc"><code>[Ss]creenshot</code> matches "Screenshot" or "screenshot"</td></tr>
                <tr><td><code>(?i)</code></td><td>Case-insensitive (put at start)</td><td class="cs-desc"><code>(?i)screenshot</code> matches "SCREENSHOT", "Screenshot"</td></tr>
                <tr><td><code>a|b</code></td><td>Either "a" or "b"</td><td class="cs-desc"><code>invoice|receipt</code> matches either word</td></tr>
            </tbody>
        </table>
        <div class="cs-example">
            <strong>Common examples</strong>
            <div><code>^INV-\d{4}-\d+</code> <span class="cs-arrow">&#8594;</span> Invoices <span class="cs-arrow">&mdash;</span> <span class="cs-desc">files like INV-2026-001.pdf</span></div>
            <div><code>(?i)screenshot</code> <span class="cs-arrow">&#8594;</span> Screenshots <span class="cs-arrow">&mdash;</span> <span class="cs-desc">any file with "screenshot" in the name</span></div>
            <div><code>^backup_.*\.zip</code> <span class="cs-arrow">&#8594;</span> Backups <span class="cs-arrow">&mdash;</span> <span class="cs-desc">files like backup_2026-10-03.zip</span></div>
            <div><code>(?i)^(meeting|standup)_notes</code> <span class="cs-arrow">&#8594;</span> Meeting Notes <span class="cs-arrow">&mdash;</span> <span class="cs-desc">meeting_notes.docx, Standup_Notes.pdf</span></div>
        </div>
        <p style="font-size:11px;color:var(--muted);margin-top:8px">Tip: Use the Rule Tester above to try your pattern before saving.</p>
    </div>
</div>

<!-- Step 6: File Categories -->
<div class="chart-card step-fallback">
    <div class="section-header">
        <h3><span class="step-badge fallback">6</span>File Categories</h3>
    </div>
    <div class="tree" id="catContainer"></div>
    <div class="add-row" style="margin-top:10px">
        <input type="text" id="newCatInput" placeholder="Category name (e.g. Documents/Reports or Misc)" onkeydown="if(event.key==='Enter')addCategory()">
        <button class="btn btn-sm btn-primary" onclick="addCategory()">Add</button>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
let S = {};

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
}

function escapeHtml(s) { const el = document.createElement('div'); el.textContent = s; return el.innerHTML; }

function makeTag(text, onRemove) {
    const t = document.createElement('span');
    t.className = 'tag';
    t.innerHTML = escapeHtml(text) + '<button>&times;</button>';
    t.querySelector('button').addEventListener('click', function() {
        const node = t.closest('.tree-node');
        t.remove();
        if (node) { const countEl = node.querySelector('.tree-count'); if (countEl) { const n = node.querySelectorAll('.tag-list .tag').length; countEl.textContent = n + ' ext' + (n !== 1 ? 's' : ''); } }
        if (onRemove) onRemove();
    });
    return t;
}

// --- Render functions ---

function toggleTreeNode(el) {
    const node = el.closest('.tree-node');
    node.classList.toggle('open');
}

function renderCategories() {
    const c = document.getElementById('catContainer');
    c.innerHTML = '';
    const groups = {};
    const flat = [];
    for (const [name, exts] of Object.entries(S.categories)) {
        const slash = name.indexOf('/');
        if (slash > 0) {
            const parent = name.slice(0, slash);
            const child = name.slice(slash + 1);
            if (!groups[parent]) groups[parent] = [];
            groups[parent].push({full: name, child, exts});
        } else {
            flat.push({full: name, child: null, exts});
        }
    }
    for (const [parent, children] of Object.entries(groups)) {
        const totalExts = children.reduce((s, ch) => s + ch.exts.length, 0);
        const groupNode = document.createElement('div');
        groupNode.className = 'tree-node tree-group';
        const eParent = escapeHtml(parent);
        let groupHtml = '<div class="tree-row" onclick="toggleTreeNode(this)">'
            + '<span class="tree-chevron">&#9654;</span>'
            + '<span class="tree-name" style="font-weight:700">' + eParent + '</span>'
            + '<span class="tree-count">' + children.length + ' sub, ' + totalExts + ' ext' + (totalExts !== 1 ? 's' : '') + '</span>'
            + '</div><div class="tree-body">';
        children.forEach(ch => {
            const eFull = escapeHtml(ch.full);
            const eChild = escapeHtml(ch.child);
            groupHtml += '<div class="tree-node tree-sub" data-name="' + eFull + '">'
                + '<div class="tree-row" onclick="toggleTreeNode(this)">'
                + '<span class="tree-chevron">&#9654;</span>'
                + '<span class="tree-name">' + eChild + '</span>'
                + '<span class="tree-count">' + ch.exts.length + ' ext' + (ch.exts.length !== 1 ? 's' : '') + '</span>'
                + '<button class="tree-remove" onclick="event.stopPropagation();removeCategory(\'' + eFull + '\')">&times;</button>'
                + '</div>'
                + '<div class="tree-body"><div class="tag-list"></div>'
                + '<div class="add-row"><input type="text" placeholder=".ext" onkeydown="if(event.key===\'Enter\')addExt(this,\'' + eFull + '\')"><button class="btn btn-sm btn-primary" onclick="addExt(this.previousElementSibling,\'' + eFull + '\')">Add</button></div>'
                + '</div></div>';
        });
        groupHtml += '</div>';
        groupNode.innerHTML = groupHtml;
        c.appendChild(groupNode);
        groupNode.querySelectorAll('.tree-sub').forEach((sub, i) => {
            const tagList = sub.querySelector('.tag-list');
            children[i].exts.forEach(ext => tagList.appendChild(makeTag(ext)));
        });
    }
    for (const item of flat) {
        const node = document.createElement('div');
        node.className = 'tree-node';
        node.dataset.name = item.full;
        const eName = escapeHtml(item.full);
        node.innerHTML = '<div class="tree-row" onclick="toggleTreeNode(this)">'
            + '<span class="tree-chevron">&#9654;</span>'
            + '<span class="tree-name">' + eName + '</span>'
            + '<span class="tree-count">' + item.exts.length + ' ext' + (item.exts.length !== 1 ? 's' : '') + '</span>'
            + '<button class="tree-remove" onclick="event.stopPropagation();removeCategory(\'' + eName + '\')">&times;</button>'
            + '</div>'
            + '<div class="tree-body">'
            + '<div class="tag-list"></div>'
            + '<div class="add-row"><input type="text" placeholder=".ext" onkeydown="if(event.key===\'Enter\')addExt(this,\'' + eName + '\')"><button class="btn btn-sm btn-primary" onclick="addExt(this.previousElementSibling,\'' + eName + '\')">Add</button></div>'
            + '</div>';
        c.appendChild(node);
        const tagList = node.querySelector('.tag-list');
        item.exts.forEach(ext => tagList.appendChild(makeTag(ext)));
    }
}

function renderClients() {
    const c = document.getElementById('clientContainer');
    c.innerHTML = '';
    for (const [name, keywords] of Object.entries(S.clients)) {
        const card = document.createElement('div');
        card.className = 'cat-card';
        card.dataset.name = name;
        card.innerHTML = '<div class="cat-header"><strong>' + escapeHtml(name) + '</strong>'
            + '<button class="btn btn-sm btn-danger" onclick="removeClient(\'' + escapeHtml(name) + '\')">&times;</button></div>'
            + '<div class="tag-list" id="client-tags-' + escapeHtml(name) + '"></div>'
            + '<div class="add-row"><input type="text" placeholder="Keyword" onkeydown="if(event.key===\'Enter\')addKeyword(this,\'' + escapeHtml(name) + '\')"><button class="btn btn-sm btn-primary" onclick="addKeyword(this.previousElementSibling,\'' + escapeHtml(name) + '\')">Add</button></div>';
        c.appendChild(card);
        const tagList = card.querySelector('.tag-list');
        keywords.forEach(kw => tagList.appendChild(makeTag(kw)));
    }
}

function subcatCardHtml(full, label, rules) {
    const eFull = escapeHtml(full);
    const eLabel = escapeHtml(label);
    return '<div class="cat-card" data-name="' + eFull + '">'
        + '<div class="cat-header"><strong>' + eLabel + '</strong>'
        + '<button class="btn btn-sm btn-danger" onclick="removeSubcat(\'' + eFull + '\')">&times;</button></div>'
        + '<div style="margin-bottom:8px"><label style="font-size:11px;color:var(--muted);font-weight:600">Keywords</label>'
        + '<div class="tag-list" data-role="subcat-kw"></div>'
        + '<div class="add-row"><input type="text" placeholder="keyword" onkeydown="if(event.key===\'Enter\')addSubcatKw(this,\'' + eFull + '\')"><button class="btn btn-sm btn-primary" onclick="addSubcatKw(this.previousElementSibling,\'' + eFull + '\')">Add</button></div></div>'
        + '<div><label style="font-size:11px;color:var(--muted);font-weight:600">Extensions</label>'
        + '<div class="tag-list" data-role="subcat-ext"></div>'
        + '<div class="add-row"><input type="text" placeholder=".ext" onkeydown="if(event.key===\'Enter\')addSubcatExt(this,\'' + eFull + '\')"><button class="btn btn-sm btn-primary" onclick="addSubcatExt(this.previousElementSibling,\'' + eFull + '\')">Add</button></div></div>'
        + '</div>';
}

function populateSubcatTags(container, rules) {
    const kwList = container.querySelector('[data-role="subcat-kw"]');
    const extList = container.querySelector('[data-role="subcat-ext"]');
    (rules.keywords || []).forEach(kw => kwList.appendChild(makeTag(kw)));
    (rules.extensions || []).forEach(ext => extList.appendChild(makeTag(ext)));
}

function renderSubcats() {
    const c = document.getElementById('subcatContainer');
    c.innerHTML = '';
    const groups = {};
    const flat = [];
    for (const [name, rules] of Object.entries(S.client_subcategories)) {
        const slash = name.indexOf('/');
        if (slash > 0) {
            const parent = name.slice(0, slash);
            const child = name.slice(slash + 1);
            if (!groups[parent]) groups[parent] = [];
            groups[parent].push({full: name, child, rules});
        } else {
            flat.push({full: name, rules});
        }
    }
    for (const [parent, children] of Object.entries(groups)) {
        const groupNode = document.createElement('div');
        groupNode.className = 'tree-node tree-group';
        const totalKw = children.reduce((s, ch) => s + (ch.rules.keywords||[]).length, 0);
        const totalExt = children.reduce((s, ch) => s + (ch.rules.extensions||[]).length, 0);
        let html = '<div class="tree-row" onclick="toggleTreeNode(this)">'
            + '<span class="tree-chevron">&#9654;</span>'
            + '<span class="tree-name" style="font-weight:700">' + escapeHtml(parent) + '</span>'
            + '<span class="tree-count">' + children.length + ' sub, ' + totalKw + ' kw, ' + totalExt + ' ext</span>'
            + '</div><div class="tree-body" style="padding-left:0">';
        children.forEach(ch => { html += subcatCardHtml(ch.full, ch.child, ch.rules); });
        html += '</div>';
        groupNode.innerHTML = html;
        c.appendChild(groupNode);
        groupNode.querySelectorAll('.cat-card').forEach((card, i) => {
            populateSubcatTags(card, children[i].rules);
        });
    }
    for (const item of flat) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = subcatCardHtml(item.full, item.full, item.rules);
        const card = wrapper.firstChild;
        c.appendChild(card);
        populateSubcatTags(card, item.rules);
    }
}

function renderIgnoreList() {
    const c = document.getElementById('ignoreList');
    c.innerHTML = '';
    S.ignore_list.forEach(p => c.appendChild(makeTag(p)));
}

function renderRegex() {
    const tbody = document.getElementById('regexBody');
    tbody.innerHTML = '';
    for (const [pattern, folder] of Object.entries(S.regex_rules)) {
        tbody.innerHTML += '<tr><td><code>' + escapeHtml(pattern) + '</code></td><td>' + escapeHtml(folder) + '</td>'
            + '<td><button class="btn btn-sm btn-danger" onclick="removeRegex(\'' + escapeHtml(pattern).replace(/'/g, "\\'") + '\')">&times;</button></td></tr>';
    }
}

function renderAll() {
    document.getElementById('cfgFolder').value = S.downloads_folder;
    document.getElementById('cfgDebounce').value = S.debounce_seconds;
    document.getElementById('cfgNotify').checked = S.notifications_enabled;
    renderWatchedFolders();
    renderCategories();
    renderClients();
    renderSubcats();
    renderIgnoreList();
    renderRegex();
}

// --- Collect current state from DOM ---

function collectState() {
    const data = {};
    data.downloads_folder = document.getElementById('cfgFolder').value;
    data.debounce_seconds = parseInt(document.getElementById('cfgDebounce').value) || 3;
    data.notifications_enabled = document.getElementById('cfgNotify').checked;
    data.watched_folders = S.watched_folders || [];

    data.categories = {};
    document.querySelectorAll('#catContainer .tree-node[data-name]').forEach(node => {
        const name = node.dataset.name;
        const tagList = node.querySelector(':scope > .tree-body > .tag-list') || node.querySelector('.tag-list');
        const exts = Array.from(tagList.querySelectorAll('.tag')).map(t => t.textContent.replace('×', '').trim());
        data.categories[name] = exts;
    });

    data.clients = {};
    document.querySelectorAll('#clientContainer .cat-card').forEach(card => {
        const name = card.dataset.name;
        const kws = Array.from(card.querySelectorAll('.tag-list .tag')).map(t => t.textContent.replace('×', '').trim());
        data.clients[name] = kws;
    });

    data.client_subcategories = {};
    document.querySelectorAll('#subcatContainer .cat-card[data-name]').forEach(card => {
        const name = card.dataset.name;
        const kws = Array.from(card.querySelectorAll('[data-role="subcat-kw"] .tag')).map(t => t.textContent.replace('×', '').trim());
        const exts = Array.from(card.querySelectorAll('[data-role="subcat-ext"] .tag')).map(t => t.textContent.replace('×', '').trim());
        data.client_subcategories[name] = { keywords: kws, extensions: exts };
    });

    data.ignore_list = Array.from(document.querySelectorAll('#ignoreList .tag')).map(t => t.textContent.replace('×', '').trim());

    data.regex_rules = {};
    document.querySelectorAll('#regexBody tr').forEach(tr => {
        const cells = tr.querySelectorAll('td');
        if (cells.length >= 2) {
            data.regex_rules[cells[0].textContent.trim()] = cells[1].textContent.trim();
        }
    });

    return data;
}

// --- Add/Remove actions ---

function addExt(input, catName) {
    const v = input.value.trim();
    if (!v) return;
    const ext = v.startsWith('.') ? v : '.' + v;
    const node = input.closest('.tree-node') || input.closest('.cat-card');
    const tagList = node.querySelector('.tag-list');
    tagList.appendChild(makeTag(ext));
    input.value = '';
    const countEl = node.querySelector('.tree-count');
    if (countEl) { const n = node.querySelectorAll('.tag-list .tag').length; countEl.textContent = n + ' ext' + (n !== 1 ? 's' : ''); }
}

function addCategory() {
    const input = document.getElementById('newCatInput');
    const name = input.value.trim();
    if (!name) return;
    S.categories[name] = [];
    renderCategories();
    input.value = '';
}

function removeCategory(name) {
    delete S.categories[name];
    renderCategories();
}

function addKeyword(input, clientName) {
    const v = input.value.trim();
    if (!v) return;
    const tagList = input.closest('.cat-card').querySelector('.tag-list');
    tagList.appendChild(makeTag(v));
    input.value = '';
}

function addClient() {
    const input = document.getElementById('newClientInput');
    const name = input.value.trim();
    if (!name) return;
    S.clients[name] = [];
    renderClients();
    input.value = '';
}

function removeClient(name) {
    delete S.clients[name];
    renderClients();
}

function addSubcatKw(input, subcatName) {
    const v = input.value.trim();
    if (!v) return;
    const card = input.closest('.cat-card');
    const tagList = card.querySelector('[data-role="subcat-kw"]');
    tagList.appendChild(makeTag(v));
    input.value = '';
}

function addSubcatExt(input, subcatName) {
    const v = input.value.trim();
    if (!v) return;
    const ext = v.startsWith('.') ? v : '.' + v;
    const card = input.closest('.cat-card');
    const tagList = card.querySelector('[data-role="subcat-ext"]');
    tagList.appendChild(makeTag(ext));
    input.value = '';
}

function addSubcat() {
    const input = document.getElementById('newSubcatInput');
    const name = input.value.trim();
    if (!name) return;
    S.client_subcategories[name] = { keywords: [], extensions: [] };
    renderSubcats();
    input.value = '';
}

function removeSubcat(name) {
    delete S.client_subcategories[name];
    renderSubcats();
}

function addIgnore() {
    const input = document.getElementById('ignoreInput');
    const v = input.value.trim();
    if (!v) return;
    document.getElementById('ignoreList').appendChild(makeTag(v));
    input.value = '';
}

function addRegex() {
    const pi = document.getElementById('regexPatternInput');
    const fi = document.getElementById('regexFolderInput');
    const pattern = pi.value.trim();
    const folder = fi.value.trim();
    if (!pattern || !folder) return;
    S.regex_rules[pattern] = folder;
    renderRegex();
    pi.value = '';
    fi.value = '';
    pi.focus();
}

function removeRegex(pattern) {
    delete S.regex_rules[pattern];
    renderRegex();
}

// --- Save / Reset ---

async function saveAll() {
    const data = collectState();
    const r = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const d = await r.json();
    if (d.ok) {
        S = data;
        showToast('Settings saved');
    } else {
        showToast('Error saving settings');
    }
}

async function resetAll() {
    if (!confirm('Reset all settings to code defaults?')) return;
    const r = await fetch('/api/settings/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    });
    const d = await r.json();
    if (d.ok) {
        showToast('Settings reset to defaults');
        await loadSettings();
    }
}

function exportSettings() {
    const data = collectState();
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'fileSorter-settings.json';
    a.click();
    URL.revokeObjectURL(url);
    showToast('Settings exported');
}

function importSettings(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async function(e) {
        try {
            const data = JSON.parse(e.target.result);
            S = data;
            renderAll();
            showToast('Settings imported — click Save to apply');
        } catch (err) {
            showToast('Invalid JSON file');
        }
    };
    reader.readAsText(file);
    input.value = '';
}

function renderWatchedFolders() {
    const c = document.getElementById('watchedFolders');
    c.innerHTML = '';
    (S.watched_folders || []).forEach((wf, idx) => {
        const rules = wf.rules || {};
        const card = document.createElement('div');
        card.className = 'wf-card';
        const ruleItems = [
            {key: 'ignore_list', label: 'Ignore List', step: 3},
            {key: 'client_match', label: 'Client Match', step: 4},
            {key: 'regex_rules', label: 'Regex Rules', step: 5},
            {key: 'extension_categories', label: 'Extension Categories', step: 6},
        ];
        let rulesHtml = '';
        ruleItems.forEach(r => {
            const checked = rules[r.key] !== false;
            rulesHtml += '<div class="wf-rule' + (checked ? '' : ' disabled') + '">'
                + '<input type="checkbox" id="wf'+idx+'_'+r.key+'"' + (checked ? ' checked' : '')
                + ' onchange="toggleWfRule('+idx+',\''+r.key+'\',this.checked)">'
                + '<label for="wf'+idx+'_'+r.key+'">'+r.label+'</label></div>';
        });
        const enabled = wf.enabled !== false;
        card.innerHTML = '<div class="wf-header">'
            + '<div class="wf-toggle"><input type="checkbox" id="wfEn'+idx+'"'+(enabled?' checked':'')
            + ' onchange="toggleWfEnabled('+idx+',this.checked)"><label for="wfEn'+idx+'">'+(enabled?'Active':'Paused')+'</label></div>'
            + '<span class="wf-path">' + escapeHtml(wf.path) + '</span>'
            + '<button class="btn btn-sm btn-danger" onclick="removeWatchedFolder('+idx+')" style="padding:3px 8px">&times;</button>'
            + '</div>'
            + '<div class="wf-rules">' + rulesHtml + '</div>';
        c.appendChild(card);
    });
}

function toggleWfEnabled(idx, val) {
    S.watched_folders[idx].enabled = val;
    renderWatchedFolders();
}

function toggleWfRule(idx, key, val) {
    if (!S.watched_folders[idx].rules) S.watched_folders[idx].rules = {};
    S.watched_folders[idx].rules[key] = val;
    const el = document.getElementById('wf'+idx+'_'+key).closest('.wf-rule');
    el.classList.toggle('disabled', !val);
}

function addWatchedFolder() {
    const input = document.getElementById('newWatchFolder');
    const path = input.value.trim();
    if (!path) return;
    if (!S.watched_folders) S.watched_folders = [];
    S.watched_folders.push({
        path: path, enabled: true,
        rules: {ignore_list: true, client_match: true, regex_rules: true, extension_categories: true}
    });
    renderWatchedFolders();
    input.value = '';
}

function removeWatchedFolder(idx) {
    S.watched_folders.splice(idx, 1);
    renderWatchedFolders();
}

async function testSort() {
    const filename = document.getElementById('testFilename').value.trim();
    if (!filename) return;
    const r = await fetch('/api/test-sort', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filename})
    });
    const d = await r.json();
    const el = document.getElementById('testResult');
    const allSteps = [
        {step:1, name:'Temp File'}, {step:2, name:'Dotfile'}, {step:3, name:'Ignore List'},
        {step:4, name:'Client Match'}, {step:5, name:'Regex Rules'},
        {step:6, name:'Extension'}, {step:7, name:'Unknown'}
    ];
    const hitStep = d.steps[d.steps.length - 1];
    let html = '<div class="test-outcome ' + d.outcome + '">';
    if (d.outcome === 'sort') {
        html += '<span>&#10004;</span> <span>' + escapeHtml(d.reason) + '</span>';
    } else {
        html += '<span>&#10007;</span> <span>' + escapeHtml(d.reason) + '</span>';
    }
    html += '</div><div class="test-steps">';
    for (const s of allSteps) {
        const found = d.steps.find(x => x.step === s.step);
        let cls = '';
        if (found && found.matched) {
            cls = d.outcome === 'sort' ? 'hit-sort' : 'hit-skip';
        } else if (found) {
            cls = 'pass';
        } else {
            cls = '';
        }
        html += '<div class="test-step ' + cls + '">';
        html += '<span class="ts-num">' + s.step + '</span>';
        html += '<span class="ts-label">' + s.name + '</span>';
        if (found && found.detail) html += '<span class="ts-detail">' + escapeHtml(found.detail) + '</span>';
        html += '</div>';
    }
    html += '</div>';
    el.innerHTML = html;
    el.classList.add('visible');
}

async function loadSettings() {
    const r = await fetch('/api/settings');
    S = await r.json();
    renderAll();
}

loadSettings();
</script>
</body>
</html>"""


def main():
    log_dir = Path(__file__).parent / "logs"
    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = DailyLogHandler(log_dir)
    file_handler.setFormatter(fmt)
    logger = logging.getLogger("fileSorter")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(logging.StreamHandler())

    db.init_db()
    config.load_overrides()

    print("Dashboard running at http://localhost:5000")
    webbrowser.open("http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
