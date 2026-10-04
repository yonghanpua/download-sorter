import fnmatch
import logging
import os
import re
import shutil
from pathlib import Path

import config
import db
import notify

log = logging.getLogger("fileSorter")


def is_locked(path: Path) -> bool:
    try:
        os.rename(str(path), str(path))
        return False
    except (PermissionError, OSError):
        return True


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


def get_client_project(path: Path, client: str) -> str | None:
    project_map = config.CLIENT_PROJECT_MAP.get(client, {})
    name_lower = path.stem.lower()
    for keyword, project in project_map.items():
        if keyword in name_lower:
            return project
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


def dry_run(filename: str, rules: dict = None) -> dict | None:
    """Dry-run: return where a file would be sorted without moving it."""
    if rules is None:
        rules = {"ignore_list": True, "client_match": True,
                 "regex_rules": True, "extension_categories": True}
    path = Path(filename)
    if is_temp_file(path):
        return {"skipped": True, "reason": "Temp file"}
    if path.name.startswith("."):
        return {"skipped": True, "reason": "Dot file"}
    if rules.get("ignore_list", True) and is_ignored(path):
        return {"skipped": True, "reason": "Ignore list"}

    if rules.get("client_match", True):
        client = get_client(path)
    else:
        client = None

    if client:
        project = get_client_project(path, client)
        subcategory = get_client_subcategory(path)
        dest_parts = [client]
        if project:
            dest_parts.append(project)
        if subcategory:
            dest_parts.append(subcategory)
        return {"category": client, "rule": "Client Match",
                "dest": "/".join(dest_parts), "skipped": False}

    if rules.get("regex_rules", True):
        regex_cat = get_regex_category(path)
    else:
        regex_cat = None
    if regex_cat:
        return {"category": regex_cat, "rule": "Regex Rule",
                "dest": regex_cat, "skipped": False}

    if not rules.get("extension_categories", True):
        return {"skipped": True, "reason": "Extension categories disabled"}
    cat = get_category(path)
    if cat is None:
        return {"skipped": True, "reason": "Unknown extension"}
    return {"category": cat, "rule": "Extension",
            "dest": cat, "skipped": False}


def sort_file(path: Path, base: Path = None, rules: dict = None) -> Path | None:
    if base is None:
        base = config.DOWNLOADS_FOLDER
    if rules is None:
        rules = {"ignore_list": True, "client_match": True,
                 "regex_rules": True, "extension_categories": True}
    if not path.is_file():
        return None
    if is_temp_file(path):
        return None
    if path.name.startswith("."):
        return None
    if rules.get("ignore_list", True) and is_ignored(path):
        return None
    if is_locked(path):
        log.debug("Skipped %s: file is open by another process", path.name)
        return None

    if rules.get("client_match", True):
        client = get_client(path)
    else:
        client = None
    rule = ""
    if client:
        project = get_client_project(path, client)
        subcategory = get_client_subcategory(path)
        client_dir = base / client
        if project:
            client_dir = client_dir / project
        if subcategory:
            dest_dir = client_dir / subcategory
        else:
            dest_dir = client_dir
        category = client
        rule = "Client Match"
    else:
        if rules.get("regex_rules", True):
            regex_cat = get_regex_category(path)
        else:
            regex_cat = None
        if regex_cat:
            dest_dir = base / regex_cat
            category = regex_cat
            rule = "Regex Rule"
        else:
            if not rules.get("extension_categories", True):
                return None
            cat = get_category(path)
            if cat is None:
                return None
            dest_dir = base / cat
            category = cat
            rule = "Extension"

    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = resolve_duplicate(dest_dir / path.name)
    try:
        shutil.move(str(path), str(dest))
    except (PermissionError, OSError) as e:
        log.warning("Skipped %s: %s", path.name, e)
        return None

    db.record_move(path, dest, category, rule)
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


def sweep(base: Path = None, output: Path = None) -> int:
    if base is None:
        base = config.DOWNLOADS_FOLDER
    if output is None:
        output = base
    count = 0
    for item in list(base.iterdir()):
        if item.is_file():
            if sort_file(item, output):
                count += 1
    if count:
        db.record_sweep(count)
        notify.sweep_complete(count)
    return count
