import fnmatch
import logging
import re
import shutil
from pathlib import Path

import config
import db

log = logging.getLogger("fileSorter")


def is_temp_file(path: Path) -> bool:
    return path.suffix.lower() in config.TEMP_EXTENSIONS


def is_ignored(path: Path) -> bool:
    name = path.name
    for pattern in config.IGNORE_LIST:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name.lower(), pattern.lower()):
            return True
    return False


def get_regex_category(path: Path) -> str | None:
    if not config.REGEX_RULES:
        return None
    name = path.name
    for pattern, folder in config.REGEX_RULES.items():
        if re.search(pattern, name):
            return folder
    return None


def get_category(path: Path) -> str | None:
    return config.EXTENSION_MAP.get(path.suffix.lower())


def get_client(path: Path) -> str | None:
    name_lower = path.name.lower()
    for client, keywords in config.CLIENTS.items():
        for keyword in keywords:
            if keyword.lower() in name_lower:
                return client
    return None


def get_client_subcategory(path: Path) -> str | None:
    name_lower = path.stem.lower()
    for keyword, subcategory in config.CLIENT_KEYWORD_MAP.items():
        if keyword in name_lower:
            return subcategory
    return config.CLIENT_EXTENSION_MAP.get(path.suffix.lower())


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


def sort_file(path: Path, base: Path = None) -> Path | None:
    if base is None:
        base = config.DOWNLOADS_FOLDER
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
        category = client
    else:
        regex_cat = get_regex_category(path)
        if regex_cat:
            dest_dir = base / regex_cat
            category = regex_cat
        else:
            cat = get_category(path)
            if cat is None:
                return None
            dest_dir = base / cat
            category = cat

    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = resolve_duplicate(dest_dir / path.name)
    try:
        shutil.move(str(path), str(dest))
    except (PermissionError, OSError) as e:
        log.warning("Skipped %s: %s", path.name, e)
        return None

    db.record_move(path, dest, category)
    log.info("Moved: %s -> %s", path.name, dest.relative_to(base))
    return dest


def undo(count: int = 1) -> int:
    records = db.get_pending_undos(count)
    if not records:
        log.info("Nothing to undo")
        return 0

    undone = 0
    for record in records:
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
            continue

        db.mark_undone(record["id"])
        log.info("Undone: %s -> %s", dest.name, src_final)
        undone += 1

    return undone


def undo_selected(move_ids: list[int]) -> int:
    undone = 0
    for move_id in move_ids:
        record = db.get_move(move_id)
        if not record or record["undone"]:
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
            continue

        db.mark_undone(move_id)
        log.info("Undone: %s -> %s", dest.name, src_final)
        undone += 1

    return undone


def sweep(base: Path = None) -> int:
    if base is None:
        base = config.DOWNLOADS_FOLDER
    count = 0
    for item in list(base.iterdir()):
        if item.is_file():
            if sort_file(item, base):
                count += 1
    if count:
        db.record_sweep(count)
    return count
