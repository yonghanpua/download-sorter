# fileSorter

A Python utility that automatically organizes your Downloads folder by sorting files into categorized subfolders based on file extension.

## Features

- **Real-time sorting** — watches your Downloads folder and moves files as they arrive
- **Batch sweep** — one-command cleanup of all existing files
- **Smart download handling** — ignores incomplete downloads (`.crdownload`, `.part`, `.tmp`) until finished
- **Duplicate safety** — auto-renames with `(1)`, `(2)`, etc. instead of overwriting
- **Daily logs** — organized in `logs/yyyy/mm/dd.log` for easy tracking
- **Client sorting** — route files to client folders with sub-categories based on filename keywords
- **Background operation** — runs silently on startup via Windows Task Scheduler

## Default Categories

| Folder | Extensions |
|---|---|
| Documents | pdf, doc/docx, xls/xlsx, ppt/pptx, txt, csv, md, epub, and more |
| Images | jpg, png, gif, bmp, svg, webp, avif, heic, psd, and more |
| Media | mp3, mp4, avi, mkv, mov, wav, flac, and more |
| Archives | zip, rar, 7z, tar, gz, iso, and more |
| Installers | exe, msi, msix, appx |
| Code | py, js, ts, html, css, json, sql, and more |
| Fonts | ttf, otf, woff, woff2 |
| 3D Prints | 3mf, stl, step, obj, gcode |

Files with unrecognized extensions are left in place.

## Setup

Requires Python 3.10+.

```bash
git clone <repo-url>
cd fileSorter
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Usage

### Batch sweep (one-time sort)

```bash
.venv\Scripts\python main.py sweep
```

### Real-time watcher

```bash
.venv\Scripts\python main.py watch
```

Press `Ctrl+C` to stop.

### Options

```bash
# Sort a different folder
.venv\Scripts\python main.py sweep --folder "D:\MyFolder"

# Change log directory
.venv\Scripts\python main.py watch --log-dir "C:\Logs\fileSorter"
```

## Background Setup (Windows)

Run once from an elevated PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This registers two scheduled tasks:

| Task | Trigger | Purpose |
|---|---|---|
| `FileSorter-Watch` | On logon | Real-time watcher (no console window) |
| `FileSorter-Sweep` | Daily at 2:00 AM | Batch sweep safety net |

Start the watcher immediately:

```powershell
Start-ScheduledTask -TaskName 'FileSorter-Watch'
```

Remove both tasks:

```powershell
Unregister-ScheduledTask -TaskName 'FileSorter-Watch' -Confirm:$false
Unregister-ScheduledTask -TaskName 'FileSorter-Sweep' -Confirm:$false
```

## Client Sorting

Files whose names contain a client keyword are sorted into client folders with sub-categories instead of the default extension-based categories.

Configure clients in `config.py`:

```python
CLIENTS = {
    "AKSS": ["AKSS", "AKS24"],       # keywords to match (case-insensitive)
    "COKE": ["COKE", "CK-"],
    "Wilmar": ["Wilmar", "WIL"],
}
```

Sub-categories are matched by **keyword first, then file extension** as fallback. Configure both in `CLIENT_SUBCATEGORIES` in `config.py`:

```python
CLIENT_SUBCATEGORIES = {
    "01. Commercial": {
        "keywords": ["commercial", "proposal", "quote", "invoice"],
        "extensions": {".pdf", ".docx", ".pptx", ".xlsx"},
    },
    "02. Documentation": {
        "keywords": ["documentation", "manual", "guide", "spec"],
        "extensions": {".txt", ".md", ".csv"},
    },
    "03. Development": {
        "keywords": ["dev", "source", "code", "deploy", "build"],
        "extensions": {".py", ".js", ".sql", ".zip", ".json"},
    },
}
```

Keyword match wins over extension. For example, `AKSS_dev_report.pdf` goes to `03. Development` (keyword "dev") even though `.pdf` would normally map to `01. Commercial`.

```
Downloads/
  AKSS/
    01. Commercial/     ← AKSS_proposal.txt (keyword), AKSS_summary.pdf (extension)
    02. Documentation/  ← AKSS_manual.pdf (keyword), AKSS_notes.txt (extension)
    03. Development/    ← AKSS_dev_report.pdf (keyword), AKSS_app.zip (extension)
    AKSS_data.xyz       ← no keyword or extension match → client root
  Documents/            ← non-client files sort normally
  Images/
```

Files matching a client but not any sub-category go to the client's root folder.

## Customization

Edit `config.py` to add categories or extensions:

```python
CATEGORIES = {
    "3D Prints": {".3mf", ".stl", ".step", ".obj", ".gcode"},
    # ... existing categories
}
```

The subfolder is created automatically — no other code changes needed.

## Testing

```bash
# Run all tests
.venv\Scripts\python -m pytest test_sorter.py -v

# Run tests matching a keyword
.venv\Scripts\python -m pytest test_sorter.py -k "client"
```

## Logs

Daily log files are written to `logs/yyyy/mm/dd.log`:

```
2026-10-01 22:30:47  Moved: resume.pdf -> Documents\resume.pdf
2026-10-01 22:30:47  Moved: photo.jpg -> Images\photo.jpg
2026-10-01 22:30:47  Skipped locked.xlsx: Permission denied
```
