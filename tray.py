"""System tray interface for fileSorter."""

import logging
import os
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from config import DOWNLOADS_FOLDER
from main import DailyLogHandler
from sorter import _load_history, sweep, undo
from watcher import watch

log = logging.getLogger("fileSorter")


def _create_icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 63, 63], fill="#2563eb")
    draw.rectangle([14, 10, 50, 54], fill="white", outline="#1e40af", width=2)
    draw.line([22, 24, 42, 24], fill="#2563eb", width=2)
    draw.line([22, 32, 42, 32], fill="#2563eb", width=2)
    draw.line([22, 40, 38, 40], fill="#2563eb", width=2)
    draw.polygon([(50, 38), (58, 54), (42, 54)], fill="#f59e0b")
    return img


_observer_thread: threading.Thread | None = None
_watching = False


def _start_watcher(icon: pystray.Icon, item: pystray.MenuItem):
    global _observer_thread, _watching
    if _watching:
        icon.notify("Watcher is already running", "fileSorter")
        return
    _watching = True

    def run():
        global _watching
        try:
            watch(DOWNLOADS_FOLDER)
        finally:
            _watching = False

    _observer_thread = threading.Thread(target=run, daemon=True)
    _observer_thread.start()
    icon.notify("Watcher started", "fileSorter")


def _sweep_now(icon: pystray.Icon, item: pystray.MenuItem):
    count = sweep(DOWNLOADS_FOLDER)
    icon.notify(f"Sweep complete: {count} file(s) sorted", "fileSorter")


def _undo_last(icon: pystray.Icon, item: pystray.MenuItem):
    undone = undo(1)
    if undone:
        icon.notify(f"Undone {undone} file(s)", "fileSorter")
    else:
        icon.notify("Nothing to undo", "fileSorter")


def _undo_all(icon: pystray.Icon, item: pystray.MenuItem):
    total = len(_load_history())
    undone = undo(total)
    if undone:
        icon.notify(f"Undone {undone} file(s)", "fileSorter")
    else:
        icon.notify("Nothing to undo", "fileSorter")


def _open_downloads(icon: pystray.Icon, item: pystray.MenuItem):
    os.startfile(str(DOWNLOADS_FOLDER))


def _open_logs(icon: pystray.Icon, item: pystray.MenuItem):
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.startfile(str(log_dir))


def _quit(icon: pystray.Icon, item: pystray.MenuItem):
    icon.stop()


def _setup_logging():
    log_dir = Path(__file__).parent / "logs"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    handlers.append(DailyLogHandler(log_dir))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def main():
    _setup_logging()

    menu = pystray.Menu(
        pystray.MenuItem("Start Watcher", _start_watcher),
        pystray.MenuItem("Sweep Now", _sweep_now),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Undo Last Move", _undo_last),
        pystray.MenuItem("Undo All Moves", _undo_all),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Downloads", _open_downloads),
        pystray.MenuItem("Open Logs", _open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )

    icon = pystray.Icon("fileSorter", _create_icon_image(), "fileSorter", menu)
    icon.run()


if __name__ == "__main__":
    main()
