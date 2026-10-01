import logging
import shutil
from pathlib import Path

from config import (
    CLIENTS,
    CLIENT_EXTENSION_MAP,
    CLIENT_KEYWORD_MAP,
    DOWNLOADS_FOLDER,
    EXTENSION_MAP,
    TEMP_EXTENSIONS,
)

log = logging.getLogger("fileSorter")


def is_temp_file(path: Path) -> bool:
    return path.suffix.lower() in TEMP_EXTENSIONS


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

    client = get_client(path)
    if client:
        subcategory = get_client_subcategory(path)
        if subcategory:
            dest_dir = base / client / subcategory
        else:
            dest_dir = base / client
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

    log.info("Moved: %s -> %s", path.name, dest.relative_to(base))
    return dest


def sweep(base: Path = DOWNLOADS_FOLDER) -> int:
    count = 0
    for item in list(base.iterdir()):
        if item.is_file():
            if sort_file(item, base):
                count += 1
    return count
