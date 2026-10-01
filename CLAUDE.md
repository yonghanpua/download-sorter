# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

fileSorter — a Python utility that automatically organizes files in the Windows Downloads folder into categorized subfolders (Documents, Images, Media, Archives, Installers, Code, Fonts). Supports real-time filesystem watching, one-shot batch sweeps, and a live web dashboard.

## Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Run
.venv\Scripts\python main.py watch              # real-time watcher
.venv\Scripts\python main.py sweep              # one-time batch sort
.venv\Scripts\python main.py sweep --folder X   # sort a custom folder
.venv\Scripts\python main.py undo               # undo last move
.venv\Scripts\python main.py undo --count 5     # undo last 5 moves
.venv\Scripts\python main.py undo --count 0     # undo all moves
.venv\Scripts\python main.py migrate            # import existing logs into SQLite
.venv\Scripts\python main.py watch --log-dir logs

# Dashboard
.venv\Scripts\python dashboard.py               # web dashboard at localhost:5000

# Tests
.venv\Scripts\python -m pytest test_sorter.py -v    # all tests
.venv\Scripts\python -m pytest test_sorter.py -k "test_client"  # run tests matching keyword

# Background setup (registers Windows Task Scheduler tasks)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## Architecture

- **config.py** — category-to-extensions mapping (`CATEGORIES` dict), reverse lookup (`EXTENSION_MAP`), client keywords (`CLIENTS`), sub-category rules with keyword+extension matching (`CLIENT_SUBCATEGORIES`), ignore list (`IGNORE_LIST`), optional regex rules (`REGEX_RULES`), temp-file extensions, debounce delay, and default folder path. All tuning happens here.
- **db.py** — SQLite database layer (`fileSorter.db`). Stores move history (`moves` table with undone flag) and sweep events (`sweeps` table). Provides `record_move()`, `record_sweep()`, `get_pending_undos()`, `mark_undone()`, `get_stats()`, `get_history()`, and `migrate_from_logs()`. Uses WAL mode for concurrent access.
- **sorter.py** — core logic: `sort_file()` checks ignore list, client match (keyword priority), regex rules, then extension-based category. `sweep()` iterates the folder. `undo()` and `undo_selected()` reverse moves via the SQLite database. Skips temp/dot files and handles locked-file errors.
- **test_sorter.py** — pytest suite covering all sorting functions including undo and selective undo. Uses `tmp_path` fixtures and an autouse `_temp_db` fixture that redirects `db.DB_PATH` to a temp file.
- **dashboard.py** — Flask web app with Chart.js charts, date filtering, watcher control (via Windows Task Scheduler), and move history with selective undo. Queries SQLite directly for instant stats.
- **watcher.py** — `watchdog` filesystem observer. `DownloadHandler` debounces file events (creation + rename) by `DEBOUNCE_SECONDS` before sorting, so in-progress downloads aren't moved prematurely.
- **main.py** — CLI entry point with `watch`, `sweep`, `undo`, and `migrate` subcommands.
- **setup.ps1** — registers two Task Scheduler tasks: `FileSorter-Watch` (on logon, uses `pythonw.exe` for no console) and `FileSorter-Sweep` (daily at 2 AM).

## Key design decisions

- Extension → category mapping is the single source of truth in `config.py`. Unrecognized extensions are left in place.
- SQLite (`fileSorter.db`) is the single source of truth for move history. Log files are kept as a human-readable audit trail but are not parsed at runtime.
- Undo marks moves as `undone=1` in the database — full history is preserved.
- Duplicate resolution appends ` (1)`, ` (2)`, etc. — never overwrites.
- The watcher uses a per-file debounce timer (default 3s) so that Chrome `.crdownload` → final rename events are handled cleanly.
- `recursive=False` on the observer — only top-level files are watched, not the category subfolders.
- Priority order for sorting: temp file → dotfile → ignore list → client match → regex rules → extension category.
