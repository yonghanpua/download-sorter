import argparse
import datetime
import logging
import sys
from pathlib import Path

import config
import db


class DailyLogHandler(logging.Handler):
    """Writes log records to logs/yyyy/mm/dd.log, rolling at midnight."""

    def __init__(self, base_dir: Path):
        super().__init__()
        self._base_dir = base_dir
        self._current_date: datetime.date | None = None
        self._stream = None

    def _open(self, date: datetime.date):
        if self._stream:
            self._stream.close()
        log_dir = self._base_dir / str(date.year) / f"{date.month:02d}"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{date.day:02d}.log"
        self._stream = open(log_path, "a", encoding="utf-8")
        self._current_date = date

    def emit(self, record):
        today = datetime.date.today()
        if today != self._current_date:
            self._open(today)
        msg = self.format(record)
        self._stream.write(msg + "\n")
        self._stream.flush()

    def close(self):
        if self._stream:
            self._stream.close()
        super().close()


def setup_logging(log_dir: Path | None = None):
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir:
        handlers.append(DailyLogHandler(log_dir))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def main():
    parser = argparse.ArgumentParser(description="Sort files in your Downloads folder")
    parser.add_argument(
        "mode",
        choices=["watch", "sweep", "undo", "migrate"],
        help="'watch' for real-time, 'sweep' for batch sort, 'undo' to reverse, 'migrate' to import logs into DB",
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        help="Folder to sort (default: ~/Downloads)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory for daily log files (default: ./logs)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of moves to undo (default: 1, use 0 for all)",
    )
    args = parser.parse_args()

    db.init_db()
    config.load_overrides()
    if args.folder is None:
        args.folder = config.DOWNLOADS_FOLDER
    setup_logging(args.log_dir)
    log = logging.getLogger("fileSorter")

    if args.mode == "migrate":
        result = db.migrate_from_logs(args.log_dir, args.folder)
        if result.get("skipped"):
            log.info("Database already has data — skipping migration")
        else:
            log.info(
                "Migration complete: %d move(s), %d sweep(s) imported",
                result["moves"], result["sweeps"],
            )
    elif args.mode == "undo":
        from sorter import undo

        n = 0 if args.count == 0 else args.count
        if n == 0:
            pending = db.get_pending_undos()
            n = len(pending)
        undone = undo(n)
        log.info("Undo complete: %d file(s) restored", undone)
    elif args.mode == "sweep":
        if not args.folder.is_dir():
            log.error("Folder does not exist: %s", args.folder)
            sys.exit(1)
        from sorter import sweep

        count = sweep(args.folder)
        log.info("Sweep complete: %d file(s) sorted", count)
    else:
        if not args.folder.is_dir():
            log.error("Folder does not exist: %s", args.folder)
            sys.exit(1)
        from watcher import watch

        watch(args.folder)


if __name__ == "__main__":
    main()
