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
        ".ai",
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
