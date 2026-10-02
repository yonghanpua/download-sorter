import copy
from pathlib import Path

DOWNLOADS_FOLDER = Path.home() / "Downloads"

DEBOUNCE_SECONDS = 3

TEMP_EXTENSIONS = {
    ".crdownload", ".part", ".tmp", ".download", ".partial",
    ".opdownload", ".aria2",
}

# --- Ignore list ---
IGNORE_LIST: list[str] = [
    "desktop.ini",
    "Thumbs.db",
    ".DS_Store",
]

# --- Regex rules (optional) ---
REGEX_RULES: dict[str, str] = {
    # r"^INV-\d{4}-\d+": "Invoices",
    # r"^RPT-\d+": "Reports",
    # r"^IMG_\d{8}": "Camera Photos",
    # r"(?i)screenshot": "Screenshots",
}

CATEGORIES = {
    "Documents": {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".rtf", ".odt", ".ods", ".odp", ".csv", ".md",
        ".epub", ".mobi",
    },
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
        ".ico", ".tiff", ".tif", ".heic", ".heif", ".raw", ".psd",
        ".ai", ".avif", ".jfif", ".jxl",
    },
    "Media": {
        ".mp3", ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
        ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".m4v",
        ".webm", ".3gp",
    },
    "Archives": {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
        ".iso", ".dmg", ".cab",
    },
    "Installers": {
        ".exe", ".msi", ".msix", ".appx", ".deb", ".rpm",
    },
    "Code": {
        ".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
        ".yaml", ".yml", ".sql", ".sh", ".bat", ".ps1", ".java",
        ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php",
    },
    "Fonts": {
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
    },
    "3D Prints": {
        ".3mf", ".stl", ".step", ".obj", ".gcode",
    },
}

# --- Client-based sorting ---
CLIENTS: dict[str, list[str]] = {
    "AKSS": ["AKSS", "AKS24"],
}

CLIENT_SUBCATEGORIES: dict[str, dict] = {
    "01. Commercial": {
        "keywords": ["commercial", "proposal", "quote", "invoice", "contract", "tender"],
        "extensions": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xlsx", ".xls"},
    },
    "02. Documentation": {
        "keywords": ["documentation", "manual", "guide", "spec", "requirement", "sop"],
        "extensions": {".txt", ".md", ".csv", ".rtf", ".epub"},
    },
    "03. Development": {
        "keywords": ["dev", "source", "code", "deploy", "build", "release"],
        "extensions": {
            ".py", ".js", ".ts", ".sql", ".json", ".xml", ".yaml", ".yml",
            ".html", ".css", ".zip", ".7z", ".rar", ".tar", ".gz",
        },
    },
}

# --- Derived maps (auto-built) ---

EXTENSION_MAP: dict[str, str] = {}
CLIENT_KEYWORD_MAP: dict[str, str] = {}
CLIENT_EXTENSION_MAP: dict[str, str] = {}


def _rebuild_maps():
    global EXTENSION_MAP, CLIENT_KEYWORD_MAP, CLIENT_EXTENSION_MAP
    EXTENSION_MAP = {}
    for cat, exts in CATEGORIES.items():
        for ext in exts:
            EXTENSION_MAP[ext] = cat
    CLIENT_KEYWORD_MAP = {}
    for subcat, rules in CLIENT_SUBCATEGORIES.items():
        for kw in rules.get("keywords", []):
            CLIENT_KEYWORD_MAP[kw.lower()] = subcat
    CLIENT_EXTENSION_MAP = {}
    for subcat, rules in CLIENT_SUBCATEGORIES.items():
        for ext in rules.get("extensions", set()):
            CLIENT_EXTENSION_MAP[ext] = subcat


_rebuild_maps()

# Snapshot defaults for reset
_DEFAULTS = {
    "downloads_folder": str(DOWNLOADS_FOLDER),
    "debounce_seconds": DEBOUNCE_SECONDS,
    "categories": {k: sorted(v) for k, v in CATEGORIES.items()},
    "clients": copy.deepcopy(CLIENTS),
    "client_subcategories": {
        k: {"keywords": list(v["keywords"]), "extensions": sorted(v["extensions"])}
        for k, v in CLIENT_SUBCATEGORIES.items()
    },
    "ignore_list": list(IGNORE_LIST),
    "regex_rules": dict(REGEX_RULES),
}


def load_overrides():
    """Reset to code defaults, then apply any DB overrides."""
    global DOWNLOADS_FOLDER, DEBOUNCE_SECONDS
    global CATEGORIES, CLIENTS, CLIENT_SUBCATEGORIES
    global IGNORE_LIST, REGEX_RULES

    DOWNLOADS_FOLDER = Path(_DEFAULTS["downloads_folder"])
    DEBOUNCE_SECONDS = _DEFAULTS["debounce_seconds"]
    CATEGORIES = {k: set(v) for k, v in _DEFAULTS["categories"].items()}
    CLIENTS = copy.deepcopy(_DEFAULTS["clients"])
    CLIENT_SUBCATEGORIES = {
        k: {"keywords": list(v["keywords"]), "extensions": set(v["extensions"])}
        for k, v in _DEFAULTS["client_subcategories"].items()
    }
    IGNORE_LIST = list(_DEFAULTS["ignore_list"])
    REGEX_RULES = dict(_DEFAULTS["regex_rules"])

    try:
        import db
        overrides = db.get_all_settings()
    except Exception:
        _rebuild_maps()
        return

    if "downloads_folder" in overrides:
        DOWNLOADS_FOLDER = Path(overrides["downloads_folder"])
    if "debounce_seconds" in overrides:
        DEBOUNCE_SECONDS = overrides["debounce_seconds"]
    if "categories" in overrides:
        CATEGORIES = {k: set(v) for k, v in overrides["categories"].items()}
    if "clients" in overrides:
        CLIENTS = overrides["clients"]
    if "client_subcategories" in overrides:
        CLIENT_SUBCATEGORIES = {
            k: {"keywords": v.get("keywords", []), "extensions": set(v.get("extensions", []))}
            for k, v in overrides["client_subcategories"].items()
        }
    if "ignore_list" in overrides:
        IGNORE_LIST = overrides["ignore_list"]
    if "regex_rules" in overrides:
        REGEX_RULES = overrides["regex_rules"]

    _rebuild_maps()
