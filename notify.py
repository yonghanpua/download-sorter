"""Windows toast notifications for fileSorter."""

import logging
import threading
from pathlib import Path

import config

log = logging.getLogger("fileSorter")

APP_ID = "fileSorter"


def _send(title: str, message: str):
    if not config.NOTIFICATIONS_ENABLED:
        return
    try:
        from winotify import Notification
        toast = Notification(app_id=APP_ID, title=title, msg=message)
        toast.show()
    except Exception as e:
        log.debug("Notification failed: %s", e)


def _send_async(title: str, message: str):
    threading.Thread(target=_send, args=(title, message), daemon=True).start()


def file_sorted(filename: str, category: str):
    _send_async("File Sorted", f"{filename} → {category}")


def sweep_complete(count: int):
    if count:
        _send_async("Sweep Complete", f"{count} file(s) sorted")
