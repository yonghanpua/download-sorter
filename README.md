# fileSorter

A Python utility that automatically organizes your Downloads folder by sorting files into categorized subfolders based on file extension. Supports real-time watching, batch sweeps, undo, and a live web dashboard.

## Features

- **Real-time sorting** — watches your Downloads folder and moves files as they arrive
- **Batch sweep** — one-command cleanup of all existing files
- **Smart download handling** — ignores incomplete downloads (`.crdownload`, `.part`, `.tmp`) until finished
- **Duplicate safety** — auto-renames with `(1)`, `(2)`, etc. instead of overwriting
- **Client sorting** — route files to client folders with sub-categories based on filename keywords
- **Regex rules** — optional pattern-to-folder mapping for custom naming conventions
- **Ignore list** — skip specific files or glob patterns from being sorted
- **Undo** — reverse the last move, last N moves, or cherry-pick specific files to undo
- **SQLite history** — all moves tracked in a local database with full audit trail
- **Web dashboard** — live stats, charts, date filtering, watcher control, and selective undo
- **Daily logs** — human-readable audit trail in `logs/yyyy/mm/dd.log`
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

Requires Python 3.12+.

```bash
git clone https://github.com/yonghan/fileSorter.git
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

### Undo last move(s)

```bash
# Undo the last sorted file
.venv\Scripts\python main.py undo

# Undo the last 5 moves
.venv\Scripts\python main.py undo --count 5

# Undo all recorded moves
.venv\Scripts\python main.py undo --count 0
```

Move history is stored in `fileSorter.db` (SQLite). Undo marks moves as reversed in the database — the full history is always preserved.

### Web Dashboard

```bash
.venv\Scripts\python dashboard.py
```

Opens a dashboard at `http://localhost:5000` with:

- Category distribution (doughnut chart), hourly activity (bar chart), daily trends (line chart)
- Date picker to filter all stats and history by day
- Start/stop the watcher via Task Scheduler
- Sweep trigger button
- Move history table with checkboxes for selective undo
- File existence status indicator (exists/missing)
- Auto-refreshes every 10 seconds

### Migrate existing logs

If you have existing log files from before the SQLite migration:

```bash
.venv\Scripts\python main.py migrate
```

This imports move and sweep events from `logs/` into the database (runs once — skips if data already exists).

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

## Configuration

All settings live in `config.py`.

### Client Sorting

Files whose names contain a client keyword are sorted into client folders with sub-categories instead of the default extension-based categories.

```python
CLIENTS = {
    "AKSS": ["AKSS", "AKS24"],       # keywords to match (case-insensitive)
    "COKE": ["COKE", "CK-"],
}
```

Sub-categories are matched by **keyword first, then file extension** as fallback:

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
    01. Commercial/     <- AKSS_proposal.txt (keyword), AKSS_summary.pdf (extension)
    02. Documentation/  <- AKSS_manual.pdf (keyword), AKSS_notes.txt (extension)
    03. Development/    <- AKSS_dev_report.pdf (keyword), AKSS_app.zip (extension)
    AKSS_data.xyz       <- no keyword or extension match -> client root
  Documents/            <- non-client files sort normally
  Images/
```

### Ignore List

Prevent specific files or patterns from being sorted:

```python
IGNORE_LIST = [
    "desktop.ini",
    "*.bak",
    "temp_*",
]
```

### Regex Rules

Route files by name pattern (checked after client match, before extension fallback):

```python
REGEX_RULES = {
    r"^INV-\d{4}-\d+": "Invoices",      # INV-2024-001.pdf -> Invoices/
    r"(?i)screenshot": "Screenshots",     # Screenshot_2024.png -> Screenshots/
}
```

Leave the dict empty to disable.

### Custom Categories

Add or modify categories:

```python
CATEGORIES = {
    "3D Prints": {".3mf", ".stl", ".step", ".obj", ".gcode"},
    # ... existing categories
}
```

The subfolder is created automatically — no other code changes needed.

## Sorting Priority

Files are evaluated in this order — first match wins:

1. **Temp file** (`.crdownload`, `.part`, etc.) — skip
2. **Dotfile** (`.hidden`) — skip
3. **Ignore list** match — skip
4. **Client keyword** match — client folder with sub-category
5. **Regex rule** match — custom folder
6. **Extension category** match — category folder
7. **Unknown extension** — leave in place

## Project Structure

```
fileSorter/
├── config.py        # All extension/category/client/regex configuration
├── db.py            # SQLite database layer (moves + sweeps tables)
├── sorter.py        # Core sorting logic, undo, sweep
├── watcher.py       # Watchdog filesystem observer with debounce
├── main.py          # CLI entry point (watch, sweep, undo, migrate)
├── dashboard.py     # Flask web dashboard with Chart.js
├── test_sorter.py   # pytest test suite (67 tests)
├── setup.ps1        # Windows Task Scheduler registration
└── requirements.txt # Dependencies: watchdog, pytest, flask
```

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

## License

MIT
