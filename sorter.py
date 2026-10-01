import fnmatch
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import (
    CLIENTS,
    CLIENT_EXTENSION_MAP,
    CLIENT_KEYWORD_MAP,
    DOWNLOADS_FOLDER,
    EXTENSION_MAP,
    IGNORE_LIST,
    REGEX_RULES,
    TEMP_EXTENSIONS,
)

log = logging.getLogger("fileSorter")

HISTORY_FILE = Path(__file__).parent / ".move_history.jsonl"


def is_temp_file(path: Path) -> bool:
    return path.suffix.lower() in TEMP_EXTENSIONS


def is_ignored(path: Path) -> bool:
    name = path.name
    for pattern in IGNORE_LIST:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name.lower(), pattern.lower()):
            return True
    return False


def get_regex_category(path: Path) -> str | None:
    if not REGEX_RULES:
        return None
    name = path.name
    for pattern, folder in REGEX_RULES.items():
        if re.search(pattern, name):
            return folder
    return None


def get_category(path: Path) -> str | None:
    return EXTENSION_MAP.get(path.suffix.lower())


def get_client(path: Path) -> str | None:
    name_lower = path.name.lower()
    for client, keywords in CLIENTS.items():
        for keyword in keywords:
            if keyword.lower() in name_lower:
                return client
    return None


def get_client_subcategory(path: Path) -> str | None:
    name_lower = path.stem.lower()
    for keyword, subcategory in CLIENT_KEYWORD_MAP.items():
        if keyword in name_lower:
            return subcategory
    return CLIENT_EXTENSION_MAP.get(path.suffix.lower())


def resolve_duplicate(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def sort_file(path: Path, base: Path = DOWNLOADS_FOLDER) -> Path | None:
    if not path.is_file():
        return None
    if is_temp_file(path):
        return None
    if path.name.startswith("."):
        return None
    if is_ignored(path):
        return None

    client = get_client(path)
    if client:
        subcategory = get_client_subcategory(path)
        if subcategory:
            dest_dir = base / client / subcategory
        else:
            dest_dir = base / client
    else:
        regex_cat = get_regex_category(path)
        if regex_cat:
            dest_dir = base / regex_cat
        else:
            category = get_category(path)
            if category is None:
                return None
            dest_dir = base / category

    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = resolve_duplicate(dest_dir / path.name)
    try:
        shutil.move(str(path), str(dest))
    except (PermissionError, OSError) as e:
        log.warning("Skipped %s: %s", path.name, e)
        return None

    _record_move(path, dest)
    log.info("Moved: %s -> %s", path.name, dest.relative_to(base))
    return dest


def _record_move(src: Path, dest: Path):
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "src": str(src),
        "dest": str(dest),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    records = []
    with open(HISTORY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _save_history(records: list[dict]):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def undo(count: int = 1) -> int:
    records = _load_history()
    if not records:
        log.info("Nothing to undo")
        return 0

    undone = 0
    for _ in range(min(count, len(records))):
        record = records.pop()
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
            records.append(record)
            continue

        log.info("Undone: %s -> %s", dest.name, src_final)
        undone += 1

    _save_history(records)
    return undone


def sweep(base: Path = DOWNLOADS_FOLDER) -> int:
    count = 0
    for item in list(base.iterdir()):
        if item.is_file():
            if sort_file(item, base):
                count += 1
    return count
