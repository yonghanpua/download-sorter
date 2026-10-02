"""System tray icon for fileSorter — pystray-based status, controls, and dashboard."""

import logging
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw

import config
import db
from main import setup_logging
from sorter import sweep
from watcher import DownloadHandler

try:
    from watchdog.observers import Observer
except ImportError:
    Observer = None

log = logging.getLogger("fileSorter")

_observer: Observer | None = None
_observer_lock = threading.Lock()
_icon: Icon | None = None


def is_watching() -> bool:
    with _observer_lock:
        return _observer is not None and _observer.is_alive()


def _make_icon(watching: bool) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (22, 163, 74) if watching else (100, 116, 139)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=color)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("segoeui.ttf", 24)
    except Exception:
        font = ImageDraw.Draw(img).getfont()
    draw.text((10, 14), "fS", fill="white", font=font)
    return img


def _update_icon():
    if _icon:
        _icon.icon = _make_icon(is_watching())


def _start_watcher():
    global _observer
    with _observer_lock:
        if _observer and _observer.is_alive():
            return
        base = config.DOWNLOADS_FOLDER
        _observer = Observer()
        _observer.schedule(DownloadHandler(base), str(base), recursive=False)
        _observer.start()
        log.info("Watcher started — watching %s", base)
    _update_icon()


def _stop_watcher():
    global _observer
    with _observer_lock:
        if _observer:
            _observer.stop()
            _observer.join(timeout=5)
            _observer = None
            log.info("Watcher stopped")
    _update_icon()


def _toggle_watcher(icon, item):
    if is_watching():
        _stop_watcher()
    else:
        _start_watcher()


def _do_sweep(icon, item):
    base = config.DOWNLOADS_FOLDER
    count = sweep(base)
    log.info("Sweep complete: %d file(s) sorted", count)


def _open_dashboard(icon, item):
    webbrowser.open("http://localhost:5000")


def _start_dashboard_server():
    try:
        from dashboard import app
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        log.warning("Dashboard failed to start: %s", e)


def _quit(icon, item):
    _stop_watcher()
    icon.stop()


def _watcher_label(item):
    return "Pause Watcher" if is_watching() else "Start Watcher"


def run(start_watcher: bool = True, dashboard: bool = True):
    global _icon

    db.init_db()
    config.load_overrides()
    setup_logging(Path("logs"))

    if dashboard:
        t = threading.Thread(target=_start_dashboard_server, daemon=True)
        t.start()

    menu = Menu(
        MenuItem(_watcher_label, _toggle_watcher),
        MenuItem("Sweep Now", _do_sweep),
        Menu.SEPARATOR,
        MenuItem("Open Dashboard", _open_dashboard),
        Menu.SEPARATOR,
        MenuItem("Quit", _quit),
    )

    _icon = Icon("fileSorter", _make_icon(False), "fileSorter", menu)

    if start_watcher:
        _start_watcher()

    _icon.run()
