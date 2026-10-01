from pathlib import Path

DOWNLOADS_FOLDER = Path.home() / "Downloads"

DEBOUNCE_SECONDS = 3

TEMP_EXTENSIONS = {
    ".crdownload", ".part", ".tmp", ".download", ".partial",
    ".opdownload", ".aria2",
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
        ".3mf", ".stl", ".step", ".obj", ".gcode"
    }
}

EXTENSION_MAP: dict[str, str] = {}
for _category, _extensions in CATEGORIES.items():
    for _ext in _extensions:
        EXTENSION_MAP[_ext] = _category

# --- Client-based sorting ---
# Maps client folder name → list of keywords to match in filenames (case-insensitive)
CLIENTS: dict[str, list[str]] = {
    "AKSS": ["AKSS", "AKS24"],
    # "COKE": ["COKE", "CK-"],
    # "Wilmar": ["Wilmar", "WIL"],
}

# Sub-categories within each client folder
# Keywords are checked first (case-insensitive), then extension as fallback
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

CLIENT_KEYWORD_MAP: dict[str, str] = {}
for _subcategory, _rules in CLIENT_SUBCATEGORIES.items():
    for _kw in _rules.get("keywords", []):
        CLIENT_KEYWORD_MAP[_kw.lower()] = _subcategory

CLIENT_EXTENSION_MAP: dict[str, str] = {}
for _subcategory, _rules in CLIENT_SUBCATEGORIES.items():
    for _ext in _rules.get("extensions", set()):
        CLIENT_EXTENSION_MAP[_ext] = _subcategory
