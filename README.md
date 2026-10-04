# fileSorter

A Python utility that automatically organizes your Downloads folder by sorting files into categorized subfolders based on file extension. Supports real-time watching, batch sweeps, undo, and a live web dashboard.

## Features

- **Multi-folder watching** — watch Downloads, Desktop, or any folder with per-folder rule toggles and optional output destination (sort into a different folder)
- **Real-time sorting** — watches your folders and moves files as they arrive
- **Batch sweep** — one-command cleanup of all existing files, with configurable cron schedule for automatic sweeps
- **Smart download handling** — ignores incomplete downloads (`.crdownload`, `.part`, `.tmp`) until finished; skips files open by another process
- **Duplicate safety** — auto-renames with `(1)`, `(2)`, etc. instead of overwriting
- **Client sorting** — route files to client folders with optional project-level organization and sub-categories based on filename keywords
- **Regex rules** — optional pattern-to-folder mapping for custom naming conventions
- **Ignore list** — skip specific files or glob patterns from being sorted
- **Undo** — reverse the last move, last N moves, cherry-pick specific files, or batch undo by time range
- **SQLite history** — all moves tracked in a local database with full audit trail
- **Web dashboard** — live stats, charts, date filtering, watcher control, drag-and-drop rule testing, and selective undo
- **Multi-user profiles** — create separate profiles with different sorting rules for shared machines; switch instantly from the settings page
- **Browser settings** — edit all configuration from the dashboard with dirty-state tracking, unsaved-changes warning, import/export with confirmation, and safe reset with backup option
- **System tray icon** — pystray-based tray icon with status, Pause/Resume Watcher, Sweep Now, Open Dashboard, and Quit
- **Desktop notifications** — Windows toast notifications when files are sorted (toggle on/off in settings)
- **Daily logs** — human-readable audit trail in `logs/yyyy/mm/dd.log`
- **Background operation** — runs on startup via Task Scheduler with a system tray icon

## Default Categories

Categories support nested subcategories using `/` in the name (e.g. `Documents/PDFs`). Files are sorted into the matching subfolder automatically.

| Folder | Subcategories | Extensions |
|---|---|---|
| Documents | PDFs, Word, Spreadsheets, Presentations, Text, eBooks | pdf, doc/docx, xls/xlsx/xlsm/xlam, ppt/pptx, txt, md, csv, epub, and more |
| Images | Photos, Graphics, Vector, Design | jpg, png, gif, bmp, svg, webp, avif, heic, psd, and more |
| Media | Video, Audio | mp3, mp4, avi, mkv, mov, wav, flac, and more |
| Code | Web, Scripts, Compiled, Data | py, js, ts, cs, vbs, html, css, json, sql, sln, csproj, and more |
| Data | Power BI, Database | pbix, pbit, bak, dacpac, bacpac |
| Design | — | vsdx, vsd, drawio, dwg, dxf |
| Archives | — | zip, rar, 7z, tar, gz, iso, and more |
| Installers | — | exe, msi, msix, appx |
| Ignition | — | gwbk |
| Fonts | — | ttf, otf, woff, woff2 |
| 3D Prints | — | 3mf, stl, step, obj, gcode |

Files with unrecognized extensions are left in place. Categories without subcategories sort directly into their folder.

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

### System tray (recommended)

```bash
.venv\Scripts\python main.py tray
```

Launches a system tray icon that bundles everything: real-time watcher, web dashboard (localhost:5000), and quick actions. Right-click the tray icon for:

- **Pause/Start Watcher** — toggle file watching on/off
- **Sweep Now** — one-time batch sort
- **Open Dashboard** — open the web dashboard in your browser
- **Quit** — stop everything

The icon color indicates status: green = watching, grey = paused.

### Real-time watcher (standalone)

```bash
.venv\Scripts\python main.py watch
```

Press `Ctrl+C` to stop. For most users, `tray` mode is preferred since it includes the watcher plus dashboard and tray controls.

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
- Global category filter — filter all stats, charts, and history by category
- Date picker to filter all stats and history by day
- Start/stop the watcher (via tray integration or Task Scheduler fallback)
- Sweep trigger button
- Undo timeline — visual bar chart of moves over time; click two bars or use date pickers to select a range, then batch undo all moves in that range
- Drag-and-drop rule tester — drop files from your desktop to preview which rule matches and where they'd go, without moving anything
- Duplicate scanner — find files with `(1)`, `(2)` suffixes in sorted folders, review side-by-side with originals, and bulk delete
- Move history table with Rule column and checkboxes for selective undo
- Search/filter on history table by filename or destination
- Paginated history with rows-per-page selector (10/25/50/100) and fixed-height table
- File existence status indicator (exists/missing)
- Auto-refreshes every 10 seconds
- **Settings page** (`/settings`) — edit all config from the browser:
  - Rule tester — type any filename to see which rule matches and where it would be sorted, with linked category highlights showing when a client sub-category match came through a linked file category
  - Sorting priority pipeline — visual diagram showing the 7-step evaluation order
  - General settings (downloads folder, debounce delay, sweep schedule)
  - Sections ordered and color-coded to match sorting priority (red=skip, green=match, blue=fallback)
  - Collapsible tree view for file categories with extension counts
  - Clients (add/remove clients and keywords)
  - Client projects with keyword-based project detection per client
  - Client sub-categories with nested tree view (keywords, extensions, and linked file categories per sub-category)
  - Ignore list (glob patterns)
  - Regex rules (pattern → folder) with inline test input per rule and collapsible cheat sheet
  - Help button (?) with getting started guide covering tray mode, CLI commands, startup setup, and settings usage
  - Export/import settings as JSON with confirmation summary before applying
  - Sticky action bar with Export/Import on the left, unsaved-changes badge + Save + Reset to Defaults on the right
  - Dirty-state tracking with unsaved-changes indicator and page-leave warning
  - Reset confirmation modal listing what will be erased, with backup-first option
  - Watched folders management — add/remove folders, toggle per-folder sorting rules, set output destination
  - Profile switcher — create, rename, switch, and delete profiles with separate rules for each user
  - Changes are stored in SQLite and applied at runtime — no restart needed

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

# Sort files from Downloads into a separate destination
.venv\Scripts\python main.py sweep --output "D:\Sorted"
.venv\Scripts\python main.py watch --output "D:\Sorted"

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
| `FileSorter-Watch` | On logon | System tray icon with watcher + dashboard + cron sweep |
| `FileSorter-Sweep` | Daily at 2:00 AM | Batch sweep safety net (fallback if tray isn't running) |

Start the tray immediately:

```powershell
Start-ScheduledTask -TaskName 'FileSorter-Watch'
```

Remove both tasks:

```powershell
Unregister-ScheduledTask -TaskName 'FileSorter-Watch' -Confirm:$false
Unregister-ScheduledTask -TaskName 'FileSorter-Sweep' -Confirm:$false
```

## Configuration

Settings can be edited in two ways:

1. **Dashboard Settings page** — open the dashboard and click **Settings** in the top-right. Changes are saved to the SQLite database and applied immediately.
2. **`config.py`** — code defaults. Database overrides (from the Settings page) take priority at runtime.

To reset all overrides back to the code defaults, click **Reset to Defaults** on the Settings page.

### Client Sorting

Files whose names contain a client keyword are sorted into client folders with sub-categories instead of the default extension-based categories.

```python
CLIENTS = {
    "AKSS": ["AKSS", "AKS24"],       # keywords to match (case-insensitive)
    "COKE": ["COKE", "CK-"],
}
```

#### Client Projects (optional)

Files can be further organized into project subfolders within each client. Projects are matched by keyword in the filename — if a project keyword matches, the file goes into `Client / Project / Sub-category` instead of `Client / Sub-category`.

```python
CLIENT_PROJECTS = {
    "AKSS": {
        "Project Alpha": ["alpha", "prj-a"],
        "Project Beta": ["beta"],
    },
}
```

Example: `AKSS_alpha_proposal.pptx` → `AKSS/Project Alpha/01. Commercial/Proposals/`

If no project keyword matches, the file is sorted directly into the client's sub-category folder (same as before). Projects are fully optional — leave `CLIENT_PROJECTS` empty to disable.

#### Client Sub-categories

Sub-categories support nested paths using `/` (same as file categories). They are matched by **keyword first, then file extension** as fallback:

```python
CLIENT_SUBCATEGORIES = {
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
        "keywords": ["transmittal", "letter", "memo"],
        "extensions": {".doc", ".docx"},
    },
    "03. Documentation/Manuals": { ... },
    "03. Documentation/Specs": { ... },
    "04. Development/Source": { ... },
    "04. Development/Builds": { ... },
    "05. Data & Reporting/Dashboards": {
        "keywords": ["powerbi", "dashboard"],
        "categories": ["Data/Power BI"],   # linked file category
    },
    "05. Data & Reporting/Reports": {
        "keywords": ["report", "analytics"],
    },
    "06. Design/Drawings": {
        "keywords": ["design", "diagram", "taglist"],
        "categories": ["Design"],
    },
    "06. Design/Architecture": {
        "keywords": ["architecture"],
    },
    "07. Testing & Commissioning/Test Plans": {
        "keywords": ["testplan", "testcase"],
    },
    "07. Testing & Commissioning/Commissioning": {
        "keywords": ["commissioning", "acceptance", "punchlist", "snag"],
    },
    "08. Handover/As-Builts": {
        "keywords": ["handover", "asbuilt", "as-built"],
    },
    "08. Handover/Training": {
        "keywords": ["training"],
    },
    "09. Support/Incidents": {
        "keywords": ["incident", "rootcause"],
    },
    "09. Support/Tickets": {
        "keywords": ["support", "ticket"],
    },
}
```

Keyword match wins over extension. For example, `AKSS_dev_report.pdf` goes to `04. Development/Source` (keyword "dev") even though `.pdf` would normally map to `01. Commercial/Contracts`.

```
Downloads/
  AKSS/
    Project Alpha/                    <- project keyword "alpha" matched
      01. Commercial/
        Proposals/                    <- AKSS_alpha_proposal.pptx
      04. Development/
        Source/                       <- AKSS_alpha_dev_notes.py
      AKSS_alpha_data.xyz             <- project match, no sub-category
    01. Commercial/
      Proposals/                      <- AKSS_proposal.txt (keyword "proposal")
      Contracts/                      <- AKSS_summary.pdf (extension .pdf)
      Change Orders/                  <- AKSS_changeorder_001.docx
      Invoices/                       <- AKSS_data.xlsx (extension .xlsx)
    02. Correspondence/
      Meeting Minutes/                <- AKSS_meeting_notes.docx (keyword "meeting")
      Transmittals/                   <- AKSS_letter_001.doc (extension .doc)
    03. Documentation/
      Manuals/                        <- AKSS_manual.pdf (keyword "manual")
    04. Development/
      Source/                         <- AKSS_dev_notes.py (keyword "dev")
    05. Data & Reporting/
      Dashboards/                     <- AKSS_dashboard_v2.pbix (keyword "dashboard")
      Reports/                        <- AKSS_report_Q3.pdf (keyword "report")
    06. Design/
      Drawings/                       <- AKSS_system.vsdx (extension via Design category)
      Architecture/                   <- AKSS_architecture_overview.pdf (keyword "architecture")
    07. Testing & Commissioning/
      Test Plans/                     <- AKSS_testplan_v1.docx (keyword "testplan")
      Commissioning/                  <- AKSS_punchlist.xlsx (keyword "punchlist")
    08. Handover/
      As-Builts/                      <- AKSS_handover_pack.pdf (keyword "handover")
      Training/                       <- AKSS_training_manual.pdf (keyword "training")
    09. Support/
      Incidents/                      <- AKSS_incident_001.docx (keyword "incident")
      Tickets/                        <- AKSS_support_log.xlsx (keyword "support")
    AKSS_data.xyz                     <- no project or sub-category match
  Documents/                          <- non-client files sort normally
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

Add or modify categories. Use `/` to create nested subcategories:

```python
CATEGORIES = {
    "Documents/Reports": {".pdf", ".docx"},   # nested: Documents/Reports/
    "3D Prints": {".3mf", ".stl", ".gcode"},  # flat: 3D Prints/
    # ... existing categories
}
```

The subfolder hierarchy is created automatically — no other code changes needed.

### Sweep Schedule

Configure how often the automatic sweep runs using a cron expression:

```python
SWEEP_CRON = "0 2 * * *"    # daily at 2:00 AM (default)
```

Common schedules:

| Expression | Description |
|---|---|
| `0 2 * * *` | Daily at 2:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `*/30 * * * *` | Every 30 minutes |
| `0 8 * * 1-5` | Weekdays at 8:00 AM |
| `0 9,18 * * *` | Twice daily at 9 AM and 6 PM |

Set to an empty string to disable scheduled sweeps. The schedule runs inside the tray process — no external Task Scheduler dependency. The Settings page includes a cron cheat sheet and live preview of the next run time.

## Sorting Priority

Files are evaluated in this order — first match wins:

1. **Temp file** (`.crdownload`, `.part`, etc.) — skip
2. **Dotfile** (`.hidden`) — skip
3. **Ignore list** match — skip
4. **Locked file** (open by another process) — skip
5. **Client keyword** match — client folder with optional project + sub-category
6. **Regex rule** match — custom folder
7. **Extension category** match — category folder
8. **Unknown extension** — leave in place

## Project Structure

```
fileSorter/
├── config.py        # All extension/category/client/regex configuration
├── db.py            # SQLite database layer (moves, sweeps, settings tables)
├── sorter.py        # Core sorting logic, undo, sweep
├── watcher.py       # Watchdog filesystem observer with debounce
├── main.py          # CLI entry point (watch, sweep, undo, migrate, tray)
├── tray.py          # System tray icon with watcher, dashboard, and controls
├── notify.py        # Windows toast notifications
├── dashboard.py     # Flask web dashboard with Chart.js + settings
├── test_sorter.py   # pytest test suite (100 tests)
├── setup.ps1        # Windows Task Scheduler registration
└── requirements.txt # Dependencies: watchdog, pytest, flask, winotify, pystray, Pillow
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
