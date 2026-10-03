import copy
from pathlib import Path

DOWNLOADS_FOLDER = Path.home() / "Downloads"

DEBOUNCE_SECONDS = 3
NOTIFICATIONS_ENABLED = True
SWEEP_CRON = "0 2 * * *"

WATCHED_FOLDERS: list[dict] = [
    {
        "path": str(Path.home() / "Downloads"),
        "enabled": True,
        "rules": {
            "ignore_list": True,
            "client_match": True,
            "regex_rules": True,
            "extension_categories": True,
        },
    },
]

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
    "Documents/PDFs": {".pdf"},
    "Documents/Word": {".doc", ".docx", ".odt", ".rtf"},
    "Documents/Spreadsheets": {".xls", ".xlsx", ".ods", ".csv", ".xlsm", ".xlam"},
    "Documents/Presentations": {".ppt", ".pptx", ".odp"},
    "Documents/Text": {".txt", ".md"},
    "Documents/eBooks": {".epub", ".mobi"},
    "Images/Photos": {
        ".jpg", ".jpeg", ".png", ".heic", ".heif", ".raw", ".jfif",
    },
    "Images/Graphics": {
        ".gif", ".bmp", ".webp", ".avif", ".jxl", ".tiff", ".tif",
    },
    "Images/Vector": {".svg", ".ai"},
    "Images/Design": {".psd", ".ico"},
    "Media/Video": {
        ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".m4v",
        ".webm", ".3gp",
    },
    "Media/Audio": {
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a",
    },
    "Archives": {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
        ".iso", ".dmg", ".cab",
    },
    "Installers": {
        ".exe", ".msi", ".msix", ".appx", ".deb", ".rpm",
    },
    "Code/Web": {".html", ".css", ".js", ".ts", ".json", ".xml"},
    "Code/Scripts": {".py", ".sh", ".bat", ".ps1", ".rb", ".php", ".vbs"},
    "Code/Compiled": {
        ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs",
        ".sln", ".csproj",
    },
    "Code/Data": {".yaml", ".yml", ".sql"},
    "Data/Power BI": {".pbix", ".pbit"},
    "Data/Database": {".bak", ".dacpac", ".bacpac"},
    "Design": {".vsdx", ".vsd", ".drawio", ".dwg", ".dxf"},
    "Ignition": {".gwbk"},
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

CLIENT_PROJECTS: dict[str, dict[str, list[str]]] = {}

CLIENT_SUBCATEGORIES: dict[str, dict] = {
    "01. Commercial/Proposals": {
        "keywords": ["proposal", "quote", "tender", "bid", "rfq"],
        "extensions": {".ppt", ".pptx"},
    },
    "01. Commercial/Contracts": {
        "keywords": ["contract", "agreement", "nda"],
        "extensions": {".pdf"},
    },
    "01. Commercial/Change Orders": {
        "keywords": ["changeorder", "variation", "amendment"],
        "extensions": set(),
    },
    "01. Commercial/Invoices": {
        "keywords": ["invoice", "payment", "billing", "claim"],
        "extensions": {".xlsx", ".xls"},
    },
    "02. Correspondence/Meeting Minutes": {
        "keywords": ["minutes", "mom", "meeting", "agenda"],
        "extensions": set(),
    },
    "02. Correspondence/Transmittals": {
        "keywords": ["transmittal", "letter", "memo", "correspondence"],
        "extensions": {".doc", ".docx"},
    },
    "03. Documentation/Manuals": {
        "keywords": ["manual", "guide", "sop", "procedure"],
        "extensions": {".txt", ".md", ".rtf", ".epub"},
    },
    "03. Documentation/Specs": {
        "keywords": ["spec", "requirement", "datasheet", "documentation"],
        "extensions": {".csv"},
    },
    "04. Development/Source": {
        "keywords": ["dev", "source", "code", "script"],
        "extensions": set(),
        "categories": ["Code/Web", "Code/Scripts", "Code/Compiled", "Code/Data"],
    },
    "04. Development/Builds": {
        "keywords": ["deploy", "build", "release", "backup"],
        "extensions": set(),
        "categories": ["Archives"],
    },
    "05. Data & Reporting/Dashboards": {
        "keywords": ["powerbi", "dashboard"],
        "extensions": set(),
        "categories": ["Data/Power BI"],
    },
    "05. Data & Reporting/Reports": {
        "keywords": ["report", "analytics"],
        "extensions": set(),
    },
    "06. Design/Drawings": {
        "keywords": ["design", "diagram", "taglist"],
        "extensions": set(),
        "categories": ["Design"],
    },
    "06. Design/Architecture": {
        "keywords": ["architecture"],
        "extensions": set(),
    },
    "07. Testing & Commissioning/Test Plans": {
        "keywords": ["testplan", "testcase"],
        "extensions": set(),
    },
    "07. Testing & Commissioning/Commissioning": {
        "keywords": ["commissioning", "acceptance", "punchlist", "snag"],
        "extensions": set(),
    },
    "08. Handover/As-Builts": {
        "keywords": ["handover", "asbuilt", "as-built"],
        "extensions": set(),
    },
    "08. Handover/Training": {
        "keywords": ["training"],
        "extensions": set(),
    },
    "09. Support/Incidents": {
        "keywords": ["incident", "rootcause"],
        "extensions": set(),
    },
    "09. Support/Tickets": {
        "keywords": ["support", "ticket"],
        "extensions": set(),
    },
}

# --- Derived maps (auto-built) ---

EXTENSION_MAP: dict[str, str] = {}
CLIENT_KEYWORD_MAP: dict[str, str] = {}
CLIENT_EXTENSION_MAP: dict[str, str] = {}
CLIENT_PROJECT_MAP: dict[str, dict[str, str]] = {}


def _rebuild_maps():
    global EXTENSION_MAP, CLIENT_KEYWORD_MAP, CLIENT_EXTENSION_MAP, CLIENT_PROJECT_MAP
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
        exts = set(rules.get("extensions", set()))
        for cat_ref in rules.get("categories", []):
            if cat_ref in CATEGORIES:
                exts |= CATEGORIES[cat_ref]
        for ext in exts:
            CLIENT_EXTENSION_MAP[ext] = subcat
    CLIENT_PROJECT_MAP = {}
    for client, projects in CLIENT_PROJECTS.items():
        kw_map = {}
        for proj_name, keywords in projects.items():
            for kw in keywords:
                kw_map[kw.lower()] = proj_name
        CLIENT_PROJECT_MAP[client] = kw_map


_rebuild_maps()

# Snapshot defaults for reset
_DEFAULTS = {
    "downloads_folder": str(DOWNLOADS_FOLDER),
    "debounce_seconds": DEBOUNCE_SECONDS,
    "notifications_enabled": NOTIFICATIONS_ENABLED,
    "sweep_cron": SWEEP_CRON,
    "watched_folders": copy.deepcopy(WATCHED_FOLDERS),
    "categories": {k: sorted(v) for k, v in CATEGORIES.items()},
    "clients": copy.deepcopy(CLIENTS),
    "client_projects": copy.deepcopy(CLIENT_PROJECTS),
    "client_subcategories": {
        k: {
            "keywords": list(v["keywords"]),
            "extensions": sorted(v.get("extensions", set())),
            "categories": list(v.get("categories", [])),
        }
        for k, v in CLIENT_SUBCATEGORIES.items()
    },
    "ignore_list": list(IGNORE_LIST),
    "regex_rules": dict(REGEX_RULES),
}


def load_overrides():
    """Reset to code defaults, then apply any DB overrides."""
    global DOWNLOADS_FOLDER, DEBOUNCE_SECONDS, NOTIFICATIONS_ENABLED, SWEEP_CRON
    global CATEGORIES, CLIENTS, CLIENT_PROJECTS, CLIENT_SUBCATEGORIES
    global IGNORE_LIST, REGEX_RULES, WATCHED_FOLDERS

    DOWNLOADS_FOLDER = Path(_DEFAULTS["downloads_folder"])
    DEBOUNCE_SECONDS = _DEFAULTS["debounce_seconds"]
    NOTIFICATIONS_ENABLED = _DEFAULTS["notifications_enabled"]
    SWEEP_CRON = _DEFAULTS["sweep_cron"]
    CATEGORIES = {k: set(v) for k, v in _DEFAULTS["categories"].items()}
    CLIENTS = copy.deepcopy(_DEFAULTS["clients"])
    CLIENT_PROJECTS = copy.deepcopy(_DEFAULTS["client_projects"])
    CLIENT_SUBCATEGORIES = {
        k: {
            "keywords": list(v["keywords"]),
            "extensions": set(v.get("extensions", [])),
            "categories": list(v.get("categories", [])),
        }
        for k, v in _DEFAULTS["client_subcategories"].items()
    }
    IGNORE_LIST = list(_DEFAULTS["ignore_list"])
    REGEX_RULES = dict(_DEFAULTS["regex_rules"])
    WATCHED_FOLDERS = copy.deepcopy(_DEFAULTS["watched_folders"])

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
    if "notifications_enabled" in overrides:
        NOTIFICATIONS_ENABLED = overrides["notifications_enabled"]
    if "sweep_cron" in overrides:
        SWEEP_CRON = overrides["sweep_cron"]
    if "categories" in overrides:
        CATEGORIES = {k: set(v) for k, v in overrides["categories"].items()}
    if "clients" in overrides:
        CLIENTS = overrides["clients"]
    if "client_projects" in overrides:
        CLIENT_PROJECTS = overrides["client_projects"]
    if "client_subcategories" in overrides:
        CLIENT_SUBCATEGORIES = {
            k: {
                "keywords": v.get("keywords", []),
                "extensions": set(v.get("extensions", [])),
                "categories": list(v.get("categories", [])),
            }
            for k, v in overrides["client_subcategories"].items()
        }
    if "ignore_list" in overrides:
        IGNORE_LIST = overrides["ignore_list"]
    if "regex_rules" in overrides:
        REGEX_RULES = overrides["regex_rules"]
    if "watched_folders" in overrides:
        WATCHED_FOLDERS = overrides["watched_folders"]

    _rebuild_maps()
