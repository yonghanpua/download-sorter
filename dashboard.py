"""Live web dashboard for fileSorter — Flask app with controls + charts."""

import logging
import re
import shutil
import subprocess
import webbrowser
from collections import Counter
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from config import DOWNLOADS_FOLDER
from main import DailyLogHandler
from sorter import (
    _load_history,
    _save_history,
    resolve_duplicate,
    sweep,
    undo,
)

LOG_DIR = Path(__file__).parent / "logs"
log = logging.getLogger("fileSorter")

app = Flask(__name__)

MOVE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+Moved: (.+?) -> (.+)$"
)
UNDO_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+Undone: (.+?) -> (.+)$"
)
SWEEP_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+Sweep complete: (\d+) file"
)

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


def _parse_logs(date_filter: str | None = None) -> dict:
    moves, undos, sweeps = [], [], []
    daily_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    hourly_counts: Counter[int] = Counter()
    available_dates: set[str] = set()

    for log_file in sorted(LOG_DIR.rglob("*.log")):
        for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            m = MOVE_PATTERN.match(line)
            if m:
                ts, filename, dest = m.group(1), m.group(2), m.group(3)
                date_str = ts[:10]
                available_dates.add(date_str)
                if date_filter and date_str != date_filter:
                    daily_counts[date_str] += 1
                    continue
                category = dest.split("\\")[0]
                moves.append({"time": ts, "file": filename, "dest": dest, "category": category})
                daily_counts[date_str] += 1
                category_counts[category] += 1
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                hourly_counts[dt.hour] += 1
                continue
            u = UNDO_PATTERN.match(line)
            if u:
                date_str = u.group(1)[:10]
                available_dates.add(date_str)
                if not date_filter or date_str == date_filter:
                    undos.append({"time": u.group(1), "file": u.group(2), "dest": u.group(3)})
                continue
            s = SWEEP_PATTERN.match(line)
            if s:
                date_str = s.group(1)[:10]
                available_dates.add(date_str)
                if not date_filter or date_str == date_filter:
                    sweeps.append({"time": s.group(1), "count": int(s.group(2))})

    return {
        "total_moved": len(moves),
        "total_undone": len(undos),
        "total_sweeps": len(sweeps),
        "days_active": len(available_dates),
        "daily": dict(sorted(daily_counts.items())),
        "categories": dict(category_counts.most_common()),
        "hourly": {h: hourly_counts.get(h, 0) for h in range(24)},
        "recent": list(reversed(moves[-50:])),
        "available_dates": sorted(available_dates, reverse=True),
    }


# --- API routes ---

@app.route("/")
def index():
    return render_template_string(TEMPLATE)


@app.route("/api/stats")
def api_stats():
    date_filter = request.args.get("date")
    data = _parse_logs(date_filter if date_filter else None)
    data["watching"] = _is_task_running()
    data["history_count"] = len(_load_history())
    return jsonify(data)


@app.route("/api/history")
def api_history():
    records = _load_history()
    date_filter = request.args.get("date")
    items = []
    for i, r in enumerate(records):
        ts = r.get("time", "")
        date_str = ts[:10] if len(ts) >= 10 else ""
        if date_filter and date_str != date_filter:
            continue
        src = Path(r["src"])
        dest = Path(r["dest"])
        try:
            dest_rel = str(dest.relative_to(DOWNLOADS_FOLDER))
        except ValueError:
            dest_rel = str(dest)
        items.append({
            "index": i,
            "time": ts,
            "file": src.name,
            "dest": dest_rel,
            "exists": dest.exists(),
        })
    items.reverse()
    return jsonify({"items": items})


@app.route("/api/sweep", methods=["POST"])
def api_sweep():
    count = sweep(DOWNLOADS_FOLDER)
    return jsonify({"ok": True, "count": count})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    undone = undo(1)
    return jsonify({"ok": True, "undone": undone})


@app.route("/api/undo-all", methods=["POST"])
def api_undo_all():
    total = len(_load_history())
    undone = undo(total)
    return jsonify({"ok": True, "undone": undone})


@app.route("/api/undo-selected", methods=["POST"])
def api_undo_selected():
    indices = set(request.json.get("indices", []))
    if not indices:
        return jsonify({"ok": True, "undone": 0})

    records = _load_history()
    undone = 0
    to_keep = []

    for i, record in enumerate(records):
        if i not in indices:
            to_keep.append(record)
            continue
        dest = Path(record["dest"])
        src = Path(record["src"])
        if not dest.exists():
            log.warning("Skipped undo: %s no longer exists", dest.name)
            continue
        src.parent.mkdir(parents=True, exist_ok=True)
        src_final = resolve_duplicate(src)
        try:
            shutil.move(str(dest), str(src_final))
        except (PermissionError, OSError) as e:
            log.warning("Skipped undo %s: %s", dest.name, e)
            to_keep.append(record)
            continue
        log.info("Undone: %s -> %s", dest.name, src_final)
        undone += 1

    _save_history(to_keep)
    return jsonify({"ok": True, "undone": undone})


@app.route("/api/watcher", methods=["POST"])
def api_watcher():
    if _is_task_running():
        _stop_task()
        return jsonify({"ok": True, "watching": False})
    _start_task()
    return jsonify({"ok": True, "watching": _is_task_running()})


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>fileSorter Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
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
.chart-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
}
.chart-card h3 { font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.full-width { grid-column: 1 / -1; }
.section-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
}
.section-header h3 { margin-bottom: 0; }
.date-picker {
    padding: 5px 10px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--card); color: var(--text); font-size: 13px; cursor: pointer;
}
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
.status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    margin-right: 6px; vertical-align: middle;
}
.status-dot.on { background: var(--success); }
.status-dot.off { background: var(--muted); }
.footer { text-align: center; color: var(--muted); font-size: 11px; margin-top: 20px; }
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

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
}

async function apiPost(url, body) {
    const opts = { method: 'POST', headers: {'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    return r.json();
}

async function doSweep() {
    showToast('Sweeping...');
    const d = await apiPost('/api/sweep');
    showToast('Sweep done: ' + d.count + ' file(s) sorted');
    refresh();
}

async function toggleWatcher() {
    const btn = document.getElementById('btnWatcher');
    btn.disabled = true;
    showToast(watching ? 'Stopping watcher...' : 'Starting watcher...');
    const d = await apiPost('/api/watcher');
    watching = d.watching;
    updateWatcherBtn();
    btn.disabled = false;
    showToast(watching ? 'Watcher started' : 'Watcher stopped');
}

function updateWatcherBtn() {
    const btn = document.getElementById('btnWatcher');
    btn.textContent = watching ? 'Stop Watcher' : 'Start Watcher';
    btn.className = watching ? 'btn btn-danger' : 'btn btn-primary';
    document.getElementById('statusText').innerHTML =
        '<span class="status-dot ' + (watching ? 'on' : 'off') + '"></span>' +
        (watching ? 'Watcher running' : 'Watcher stopped');
}

function truncate(s, n) { return s.length > n ? s.slice(0, n) + '...' : s; }

function escapeHtml(s) {
    const el = document.createElement('div');
    el.textContent = s;
    return el.innerHTML;
}

function onDateChange() {
    currentDate = document.getElementById('dateFilter').value;
    refresh();
}

function getCheckedIndices() {
    return Array.from(document.querySelectorAll('.row-cb:checked')).map(cb => parseInt(cb.dataset.idx));
}

function updateUndoBar() {
    const checked = getCheckedIndices();
    const bar = document.getElementById('undoBar');
    bar.className = checked.length ? 'undo-bar visible' : 'undo-bar';
    document.getElementById('selectedCount').textContent = checked.length;
}

function toggleSelectAll() {
    const all = document.getElementById('selectAll').checked;
    document.querySelectorAll('.row-cb:not(:disabled)').forEach(cb => cb.checked = all);
    updateUndoBar();
}

async function undoSelected() {
    const indices = getCheckedIndices();
    if (!indices.length) return;
    showToast('Undoing ' + indices.length + ' file(s)...');
    const d = await apiPost('/api/undo-selected', { indices });
    showToast(d.undone ? 'Undone ' + d.undone + ' file(s)' : 'Nothing to undo');
    document.getElementById('selectAll').checked = false;
    refresh();
}

function initCharts() {
    const animOff = { animation: false };
    catChart = new Chart(document.getElementById('catChart'), {
        type: 'doughnut',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
        options: { ...animOff, responsive: true, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8, font: { size: 11 } } } } }
    });
    hourChart = new Chart(document.getElementById('hourChart'), {
        type: 'bar',
        data: { labels: Array.from({length:24}, (_,i) => String(i).padStart(2,'0')+':00'),
                datasets: [{ data: new Array(24).fill(0), backgroundColor: '#2563eb88', borderRadius: 4 }] },
        options: { ...animOff, responsive: true, plugins: { legend: { display: false } },
                   scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } }
    });
    dailyChart = new Chart(document.getElementById('dailyChart'), {
        type: 'line',
        data: { labels: [], datasets: [{ data: [], borderColor: '#2563eb', backgroundColor: '#2563eb22', fill: true, tension: 0.3, pointRadius: 4 }] },
        options: { ...animOff, responsive: true, plugins: { legend: { display: false } },
                   scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } }
    });
}

async function refresh() {
    const dateQ = currentDate ? '?date=' + currentDate : '';

    const [statsRes, histRes] = await Promise.all([
        fetch('/api/stats' + dateQ),
        fetch('/api/history' + dateQ),
    ]);
    const d = await statsRes.json();
    const h = await histRes.json();

    watching = d.watching;
    updateWatcherBtn();

    document.getElementById('sMoved').textContent = d.total_moved;
    document.getElementById('sUndone').textContent = d.total_undone;
    document.getElementById('sSweeps').textContent = d.total_sweeps;
    document.getElementById('sDays').textContent = d.days_active;

    // Update date picker options
    const sel = document.getElementById('dateFilter');
    const prev = sel.value;
    const opts = '<option value="">All dates</option>' +
        (d.available_dates || []).map(dt =>
            '<option value="' + dt + '"' + (dt === prev ? ' selected' : '') + '>' + dt + '</option>'
        ).join('');
    sel.innerHTML = opts;

    const catLabels = Object.keys(d.categories);
    const catValues = Object.values(d.categories);
    catChart.data.labels = catLabels;
    catChart.data.datasets[0].data = catValues;
    catChart.data.datasets[0].backgroundColor = COLORS.slice(0, catLabels.length);
    catChart.update();

    const hValues = Array.from({length:24}, (_,i) => d.hourly[i] || 0);
    hourChart.data.datasets[0].data = hValues;
    hourChart.update();

    dailyChart.data.labels = Object.keys(d.daily);
    dailyChart.data.datasets[0].data = Object.values(d.daily);
    dailyChart.update();

    // History table with checkboxes
    const tbody = document.getElementById('historyBody');
    tbody.innerHTML = h.items.map(item => {
        const gone = !item.exists;
        return '<tr class="' + (gone ? 'row-gone' : '') + '">' +
            '<td><input type="checkbox" class="row-cb" data-idx="' + item.index + '"' +
            (gone ? ' disabled title="File no longer exists"' : '') +
            ' onchange="updateUndoBar()"></td>' +
            '<td>' + escapeHtml(item.time.slice(0,19)) + '</td>' +
            '<td title="' + escapeHtml(item.file) + '">' + escapeHtml(truncate(item.file, 35)) + '</td>' +
            '<td title="' + escapeHtml(item.dest) + '">' + escapeHtml(truncate(item.dest, 35)) + '</td>' +
            '<td>' + (gone ? '<span style="color:var(--danger);font-size:11px">Missing</span>' :
                             '<span style="color:var(--success);font-size:11px">Exists</span>') + '</td></tr>';
    }).join('');

    updateUndoBar();
}

initCharts();
refresh();
setInterval(refresh, 10000);
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

    print("Dashboard running at http://localhost:5000")
    webbrowser.open("http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
