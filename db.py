"""SQLite database for fileSorter — move history and sweep events."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "fileSorter.db"

SCHEMA = """\
CREATE TABLE IF NOT EXISTS moves (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    src       TEXT    NOT NULL,
    dest      TEXT    NOT NULL,
    category  TEXT    NOT NULL,
    undone    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sweeps (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    count     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_moves_timestamp ON moves(timestamp);
CREATE INDEX IF NOT EXISTS idx_moves_undone    ON moves(undone);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(SCHEMA)


def record_move(src: Path, dest: Path, category: str) -> int:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO moves (timestamp, src, dest, category) VALUES (?, ?, ?, ?)",
            (ts, str(src), str(dest), category),
        )
        return cur.lastrowid


def record_sweep(count: int):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sweeps (timestamp, count) VALUES (?, ?)",
            (ts, count),
        )


def get_pending_undos(limit: int = 0) -> list[dict]:
    with _connect() as conn:
        sql = ("SELECT id, timestamp, src, dest, category "
               "FROM moves WHERE undone = 0 ORDER BY id DESC")
        if limit > 0:
            sql += f" LIMIT {limit}"
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_move(move_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, timestamp, src, dest, category, undone "
            "FROM moves WHERE id = ?",
            (move_id,),
        ).fetchone()
        return dict(row) if row else None


def mark_undone(move_id: int):
    with _connect() as conn:
        conn.execute("UPDATE moves SET undone = 1 WHERE id = ?", (move_id,))


def get_stats(date_filter: str | None = None) -> dict:
    with _connect() as conn:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT date(timestamp) FROM moves ORDER BY date(timestamp) DESC"
        ).fetchall()]

        dc = ""
        dp: list = []
        if date_filter:
            dc = "AND date(timestamp) = ?"
            dp = [date_filter]

        total_moved = conn.execute(
            f"SELECT COUNT(*) FROM moves WHERE undone = 0 {dc}", dp
        ).fetchone()[0]

        total_undone = conn.execute(
            f"SELECT COUNT(*) FROM moves WHERE undone = 1 {dc}", dp
        ).fetchone()[0]

        sw_sql = "SELECT COUNT(*) FROM sweeps"
        sw_p: list = []
        if date_filter:
            sw_sql += " WHERE date(timestamp) = ?"
            sw_p = [date_filter]
        total_sweeps = conn.execute(sw_sql, sw_p).fetchone()[0]

        categories = {}
        for r in conn.execute(
            f"SELECT category, COUNT(*) c FROM moves WHERE undone = 0 {dc} "
            "GROUP BY category ORDER BY c DESC", dp
        ).fetchall():
            categories[r[0]] = r[1]

        hourly = {h: 0 for h in range(24)}
        for r in conn.execute(
            f"SELECT CAST(strftime('%H', timestamp) AS INTEGER) h, COUNT(*) c "
            f"FROM moves WHERE undone = 0 {dc} GROUP BY h", dp
        ).fetchall():
            hourly[r[0]] = r[1]

        daily = {}
        for r in conn.execute(
            "SELECT date(timestamp) d, COUNT(*) c FROM moves "
            "WHERE undone = 0 GROUP BY d ORDER BY d"
        ).fetchall():
            daily[r[0]] = r[1]

        return {
            "total_moved": total_moved,
            "total_undone": total_undone,
            "total_sweeps": total_sweeps,
            "days_active": len(dates),
            "daily": daily,
            "categories": categories,
            "hourly": hourly,
            "available_dates": dates,
        }


def get_history(date_filter: str | None = None) -> list[dict]:
    with _connect() as conn:
        dc = ""
        dp: list = []
        if date_filter:
            dc = "AND date(timestamp) = ?"
            dp = [date_filter]
        rows = conn.execute(
            f"SELECT id, timestamp, src, dest, category, undone "
            f"FROM moves WHERE undone = 0 {dc} ORDER BY id DESC LIMIT 200", dp
        ).fetchall()
        return [dict(r) for r in rows]


def migrate_from_logs(log_dir: Path, downloads_folder: Path) -> dict:
    """Import existing log files into the database. Returns counts."""
    move_pat = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+Moved: (.+?) -> (.+)$"
    )
    undo_pat = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+Undone: (.+?) -> (.+)$"
    )
    sweep_pat = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+Sweep complete: (\d+) file"
    )

    with _connect() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM moves").fetchone()[0]
        if existing > 0:
            return {"moves": 0, "sweeps": 0, "skipped": True}

    moves_count = 0
    sweeps_count = 0
    undone_files: list[str] = []

    with _connect() as conn:
        for log_file in sorted(log_dir.rglob("*.log")):
            for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                m = move_pat.match(line)
                if m:
                    ts, filename, dest_rel = m.group(1), m.group(2), m.group(3)
                    category = dest_rel.split("\\")[0]
                    conn.execute(
                        "INSERT INTO moves (timestamp, src, dest, category) "
                        "VALUES (?, ?, ?, ?)",
                        (ts, str(downloads_folder / filename),
                         str(downloads_folder / dest_rel), category),
                    )
                    moves_count += 1
                    continue
                u = undo_pat.match(line)
                if u:
                    undone_files.append(u.group(2))
                    continue
                s = sweep_pat.match(line)
                if s:
                    conn.execute(
                        "INSERT INTO sweeps (timestamp, count) VALUES (?, ?)",
                        (s.group(1), int(s.group(2))),
                    )
                    sweeps_count += 1

        for filename in undone_files:
            conn.execute(
                "UPDATE moves SET undone = 1 WHERE id = ("
                "  SELECT MAX(id) FROM moves "
                "  WHERE src LIKE ? AND undone = 0"
                ")",
                (f"%\\{filename}",),
            )

    return {"moves": moves_count, "sweeps": sweeps_count, "skipped": False}
