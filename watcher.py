import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config
from sorter import is_temp_file, sort_file

log = logging.getLogger("fileSorter")


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, base: Path = None):
        if base is None:
            base = config.DOWNLOADS_FOLDER
        self._base = base
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: Path):
        key = str(path)
        with self._lock:
            if key in self._timers:
                self._timers[key].cancel()
            timer = threading.Timer(config.DEBOUNCE_SECONDS, self._process, args=[path])
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def _process(self, path: Path):
        with self._lock:
            self._timers.pop(str(path), None)
        if path.exists() and not is_temp_file(path):
            sort_file(path, self._base)

    def on_created(self, event):
        if event.is_directory:
            return
        self._schedule(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        if dest.parent == self._base:
            self._schedule(dest)


def watch(base: Path = None):
    if base is None:
        base = config.DOWNLOADS_FOLDER
    observer = Observer()
    observer.schedule(DownloadHandler(base), str(base), recursive=False)
    observer.start()
    log.info("Watching %s for new files...", base)
    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
