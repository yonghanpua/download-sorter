"""Live web dashboard for fileSorter — Flask app with controls, charts, and settings."""

import logging
import subprocess
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

import config
import db
from main import DailyLogHandler
from sorter import sweep, undo, undo_selected

LOG_DIR = Path(__file__).parent / "logs"
log = logging.getLogger("fileSorter")

app = Flask(__name__)

TASK_NAME = "FileSorter-Watch"


def _is_task_running() -> bool:
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
    subprocess.run(
        ["powershell", "-Command", f"Start-ScheduledTask -TaskName '{TASK_NAME}'"],
        capture_output=True, timeout=5,
    )


def _stop_task():
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
    --bg: #f1f5f9; --card: #ffffff; --text: #1e293b;
    --muted: #64748b; --border: #e2e8f0;
    --primary: #2563eb; --success: #16a34a;
    --warning: #ea580c; --danger: #dc2626; --info: #0891b2;
}
@media (prefers-color-scheme: dark) {
    :root {
        --bg: #0f172a; --card: #1e293b; --text: #f1f5f9;
        --muted: #94a3b8; --border: #334155;
    }
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 24px; max-width: 1200px; margin: 0 auto;
}
h1 { font-size: 24px; margin-bottom: 4px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
.header-left h1 { margin-bottom: 2px; }
.subtitle { color: var(--muted); font-size: 13px; }
.controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.btn {
    padding: 8px 18px; border: none; border-radius: 8px; cursor: pointer;
    font-size: 13px; font-weight: 600; color: white; transition: opacity 0.2s;
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
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th {
    text-align: left; color: var(--muted); font-weight: 600;
    padding: 6px 10px; border-bottom: 2px solid var(--border);
}
td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
tr:hover { background: var(--bg); }
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 600; background: #dbeafe; color: #1d4ed8;
}
@media (prefers-color-scheme: dark) { .badge { background: #1e3a5f; color: #93c5fd; } }
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
    data = db.get_stats(date_filter)
    data["watching"] = _is_task_running()
    return jsonify(data)


@app.route("/api/history")
def api_history():
    date_filter = request.args.get("date") or None
    items = db.get_history(date_filter)
    for item in items:
        dest = Path(item["dest"])
        item["file"] = Path(item["src"]).name
        try:
            item["dest_display"] = str(dest.relative_to(config.DOWNLOADS_FOLDER))
        except ValueError:
            item["dest_display"] = str(dest)
        item["exists"] = dest.exists()
    return jsonify({"items": items})


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
    })


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.json
    for key in ("categories", "clients", "client_subcategories",
                "ignore_list", "regex_rules", "downloads_folder",
                "debounce_seconds", "notifications_enabled"):
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
                   "debounce_seconds", "notifications_enabled"):
            db.delete_setting(k)
    config.load_overrides()
    return jsonify({"ok": True})


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
        <a href="/settings" class="btn btn-outline">Settings</a>
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
            <select id="dateFilter" class="date-picker" onchange="onDateChange()">
                <option value="">All dates</option>
            </select>
        </div>
        <canvas id="catChart"></canvas>
    </div>
    <div class="chart-card"><h3>Activity by Hour</h3><canvas id="hourChart"></canvas></div>
    <div class="chart-card full-width"><h3>Files Sorted per Day</h3><canvas id="dailyChart" height="80"></canvas></div>
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
    <table>
        <thead><tr><th style="width:30px"></th><th>Time</th><th>File</th><th>Moved To</th><th>Status</th></tr></thead>
        <tbody id="historyBody"></tbody>
    </table>
</div>

<div class="toast" id="toast"></div>
<p class="footer">fileSorter &middot; Auto-refreshes every 10s</p>

<script>
const COLORS = ['#2563eb','#16a34a','#ea580c','#8b5cf6','#ec4899','#0891b2','#d97706','#dc2626','#059669','#6366f1'];
let catChart = null, hourChart = null, dailyChart = null;
let watching = false;
let currentDate = '';
let historyItems = [];

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
function onDateChange(){currentDate=document.getElementById('dateFilter').value;refresh();}
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
    const o={animation:false};
    catChart=new Chart(document.getElementById('catChart'),{type:'doughnut',data:{labels:[],datasets:[{data:[],backgroundColor:[]}]},options:{...o,responsive:true,plugins:{legend:{position:'bottom',labels:{boxWidth:12,padding:8,font:{size:11}}}}}});
    hourChart=new Chart(document.getElementById('hourChart'),{type:'bar',data:{labels:Array.from({length:24},(_,i)=>String(i).padStart(2,'0')+':00'),datasets:[{data:new Array(24).fill(0),backgroundColor:'#2563eb88',borderRadius:4}]},options:{...o,responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}});
    dailyChart=new Chart(document.getElementById('dailyChart'),{type:'line',data:{labels:[],datasets:[{data:[],borderColor:'#2563eb',backgroundColor:'#2563eb22',fill:true,tension:0.3,pointRadius:4}]},options:{...o,responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}});
}
async function refresh(){
    const q=currentDate?'?date='+currentDate:'';
    const [sr,hr]=await Promise.all([fetch('/api/stats'+q),fetch('/api/history'+q)]);
    const d=await sr.json(), h=await hr.json();
    watching=d.watching; updateWatcherBtn();
    document.getElementById('sMoved').textContent=d.total_moved;
    document.getElementById('sUndone').textContent=d.total_undone;
    document.getElementById('sSweeps').textContent=d.total_sweeps;
    document.getElementById('sDays').textContent=d.days_active;
    const sel=document.getElementById('dateFilter'), prev=sel.value;
    sel.innerHTML='<option value="">All dates</option>'+(d.available_dates||[]).map(dt=>'<option value="'+dt+'"'+(dt===prev?' selected':'')+'>'+dt+'</option>').join('');
    catChart.data.labels=Object.keys(d.categories); catChart.data.datasets[0].data=Object.values(d.categories);
    catChart.data.datasets[0].backgroundColor=COLORS.slice(0,Object.keys(d.categories).length); catChart.update();
    hourChart.data.datasets[0].data=Array.from({length:24},(_,i)=>d.hourly[i]||0); hourChart.update();
    dailyChart.data.labels=Object.keys(d.daily); dailyChart.data.datasets[0].data=Object.values(d.daily); dailyChart.update();
    historyItems=h.items;
    renderHistory();
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
    background: #dbeafe; color: #1d4ed8; border-radius: 10px; font-size: 11px; font-weight: 600;
}
@media (prefers-color-scheme: dark) { .tag { background: #1e3a5f; color: #93c5fd; } }
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
.actions-bar {
    display: flex; gap: 8px; margin-top: 20px; padding-top: 16px;
    border-top: 1px solid var(--border);
}
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
        <button class="btn btn-danger" onclick="resetAll()">Reset to Defaults</button>
    </div>
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

<!-- Categories -->
<div class="chart-card">
    <div class="section-header">
        <h3>File Categories</h3>
        <button class="btn btn-sm btn-primary" onclick="addCategory()">+ Add Category</button>
    </div>
    <div id="catContainer"></div>
</div>

<!-- Clients -->
<div class="chart-card">
    <div class="section-header">
        <h3>Clients</h3>
        <button class="btn btn-sm btn-primary" onclick="addClient()">+ Add Client</button>
    </div>
    <div id="clientContainer"></div>
</div>

<!-- Client Sub-categories -->
<div class="chart-card">
    <div class="section-header">
        <h3>Client Sub-categories</h3>
        <button class="btn btn-sm btn-primary" onclick="addSubcat()">+ Add Sub-category</button>
    </div>
    <div id="subcatContainer"></div>
</div>

<!-- Ignore List -->
<div class="chart-card">
    <h3>Ignore List</h3>
    <div class="tag-list" id="ignoreList"></div>
    <div class="add-row">
        <input type="text" id="ignoreInput" placeholder="Pattern (e.g. *.bak, desktop.ini)" onkeydown="if(event.key==='Enter')addIgnore()">
        <button class="btn btn-sm btn-primary" onclick="addIgnore()">Add</button>
    </div>
</div>

<!-- Regex Rules -->
<div class="chart-card">
    <div class="section-header">
        <h3>Regex Rules</h3>
        <button class="btn btn-sm btn-primary" onclick="addRegex()">+ Add Rule</button>
    </div>
    <table id="regexTable">
        <thead><tr><th>Pattern</th><th>Folder</th><th style="width:40px"></th></tr></thead>
        <tbody id="regexBody"></tbody>
    </table>
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
    t.innerHTML = escapeHtml(text) + '<button onclick="this.parentElement.remove()">&times;</button>';
    if (onRemove) t.querySelector('button').addEventListener('click', onRemove);
    return t;
}

// --- Render functions ---

function renderCategories() {
    const c = document.getElementById('catContainer');
    c.innerHTML = '';
    for (const [name, exts] of Object.entries(S.categories)) {
        const card = document.createElement('div');
        card.className = 'cat-card';
        card.dataset.name = name;
        card.innerHTML = '<div class="cat-header"><strong>' + escapeHtml(name) + '</strong>'
            + '<button class="btn btn-sm btn-danger" onclick="removeCategory(\'' + escapeHtml(name) + '\')">&times;</button></div>'
            + '<div class="tag-list" id="cat-tags-' + escapeHtml(name) + '"></div>'
            + '<div class="add-row"><input type="text" placeholder=".ext" onkeydown="if(event.key===\'Enter\')addExt(this,\'' + escapeHtml(name) + '\')"><button class="btn btn-sm btn-primary" onclick="addExt(this.previousElementSibling,\'' + escapeHtml(name) + '\')">Add</button></div>';
        c.appendChild(card);
        const tagList = card.querySelector('.tag-list');
        exts.forEach(ext => tagList.appendChild(makeTag(ext)));
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

function renderSubcats() {
    const c = document.getElementById('subcatContainer');
    c.innerHTML = '';
    for (const [name, rules] of Object.entries(S.client_subcategories)) {
        const card = document.createElement('div');
        card.className = 'cat-card';
        card.dataset.name = name;
        card.innerHTML = '<div class="cat-header"><strong>' + escapeHtml(name) + '</strong>'
            + '<button class="btn btn-sm btn-danger" onclick="removeSubcat(\'' + escapeHtml(name) + '\')">&times;</button></div>'
            + '<div style="margin-bottom:8px"><label style="font-size:11px;color:var(--muted);font-weight:600">Keywords</label>'
            + '<div class="tag-list" data-role="subcat-kw"></div>'
            + '<div class="add-row"><input type="text" placeholder="keyword" onkeydown="if(event.key===\'Enter\')addSubcatKw(this,\'' + escapeHtml(name) + '\')"><button class="btn btn-sm btn-primary" onclick="addSubcatKw(this.previousElementSibling,\'' + escapeHtml(name) + '\')">Add</button></div></div>'
            + '<div><label style="font-size:11px;color:var(--muted);font-weight:600">Extensions</label>'
            + '<div class="tag-list" data-role="subcat-ext"></div>'
            + '<div class="add-row"><input type="text" placeholder=".ext" onkeydown="if(event.key===\'Enter\')addSubcatExt(this,\'' + escapeHtml(name) + '\')"><button class="btn btn-sm btn-primary" onclick="addSubcatExt(this.previousElementSibling,\'' + escapeHtml(name) + '\')">Add</button></div></div>';
        c.appendChild(card);
        const kwList = card.querySelector('[data-role="subcat-kw"]');
        const extList = card.querySelector('[data-role="subcat-ext"]');
        (rules.keywords || []).forEach(kw => kwList.appendChild(makeTag(kw)));
        (rules.extensions || []).forEach(ext => extList.appendChild(makeTag(ext)));
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

    data.categories = {};
    document.querySelectorAll('#catContainer .cat-card').forEach(card => {
        const name = card.dataset.name;
        const exts = Array.from(card.querySelectorAll('.tag-list .tag')).map(t => t.textContent.replace('×', '').trim());
        data.categories[name] = exts;
    });

    data.clients = {};
    document.querySelectorAll('#clientContainer .cat-card').forEach(card => {
        const name = card.dataset.name;
        const kws = Array.from(card.querySelectorAll('.tag-list .tag')).map(t => t.textContent.replace('×', '').trim());
        data.clients[name] = kws;
    });

    data.client_subcategories = {};
    document.querySelectorAll('#subcatContainer .cat-card').forEach(card => {
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
    const tagList = input.closest('.cat-card').querySelector('.tag-list');
    tagList.appendChild(makeTag(ext));
    input.value = '';
}

function addCategory() {
    const name = prompt('Category name:');
    if (!name) return;
    S.categories[name] = [];
    renderCategories();
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
    const name = prompt('Client name:');
    if (!name) return;
    S.clients[name] = [];
    renderClients();
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
    const name = prompt('Sub-category name (e.g. 04. Design):');
    if (!name) return;
    S.client_subcategories[name] = { keywords: [], extensions: [] };
    renderSubcats();
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
    const pattern = prompt('Regex pattern:');
    if (!pattern) return;
    const folder = prompt('Target folder:');
    if (!folder) return;
    S.regex_rules[pattern] = folder;
    renderRegex();
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
