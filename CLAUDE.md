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
.venv\Scripts\python main.py tray               # system tray with watcher + dashboard

# Dashboard (standalone)
.venv\Scripts\python dashboard.py               # web dashboard at localhost:5000

# Tests
.venv\Scripts\python -m pytest test_sorter.py -v    # all tests
.venv\Scripts\python -m pytest test_sorter.py -k "test_client"  # run tests matching keyword

# Background setup (registers Windows Task Scheduler tasks)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## Architecture

- **config.py** — category-to-extensions mapping (`CATEGORIES` dict) with nested subcategories via `/` in names (e.g. `Documents/PDFs`), reverse lookup (`EXTENSION_MAP`), client keywords (`CLIENTS`), client sub-category rules with nested paths and keyword+extension matching (`CLIENT_SUBCATEGORIES`), ignore list (`IGNORE_LIST`), optional regex rules (`REGEX_RULES`), watched folders list (`WATCHED_FOLDERS`) with per-folder rule toggles, temp-file extensions, debounce delay, and default folder path. Code defaults are snapshotted in `_DEFAULTS`. `load_overrides()` resets to defaults then applies DB overrides from the `settings` table. Other modules use `import config` (not `from config import`) so runtime overrides are visible.
- **db.py** — SQLite database layer (`fileSorter.db`). Stores move history (`moves` table with undone flag), sweep events (`sweeps` table), and config overrides (`settings` table). Settings CRUD: `get_setting()`, `save_setting()`, `delete_setting()`, `get_all_settings()`. Uses WAL mode for concurrent access.
- **sorter.py** — core logic: `sort_file()` accepts optional `rules` dict to control which sorting steps run (ignore list, client match, regex rules, extension categories). `sweep()` iterates the folder. `undo()` and `undo_selected()` reverse moves via the SQLite database. Skips temp/dot files and handles locked-file errors.
- **test_sorter.py** — pytest suite covering all sorting functions including undo and selective undo. Uses `tmp_path` fixtures and an autouse `_temp_db` fixture that redirects `db.DB_PATH` to a temp file.
- **tray.py** — `pystray` system tray icon. Bundles the watcher (background thread with multiple observers for all enabled watched folders), Flask dashboard (daemon thread), and quick-action menu (Pause/Start Watcher, Sweep Now, Open Dashboard, Quit). Icon color reflects watcher state (green=watching, grey=paused). Dashboard watcher controls talk directly to the tray's in-process watcher.
- **dashboard.py** — Flask web app with Chart.js charts, date filtering, watcher control (via tray integration or Task Scheduler fallback), move history with selective undo, and a settings page (`/settings`) for editing all config from the browser. Settings API: `GET/POST /api/settings`, `POST /api/settings/reset`. Saves overrides to the `settings` table and calls `config.load_overrides()` to apply immediately.
- **notify.py** — Windows toast notifications via `winotify`. `file_sorted()` fires per-file in watcher mode; `sweep_complete()` fires a summary after batch sweeps. Sends asynchronously on a daemon thread. Controlled by `config.NOTIFICATIONS_ENABLED`.
- **watcher.py** — `watchdog` filesystem observer. `DownloadHandler` accepts optional `rules` dict and debounces file events (creation + rename) by `DEBOUNCE_SECONDS` before sorting, so in-progress downloads aren't moved prematurely. Fires toast notifications on successful sorts.
- **main.py** — CLI entry point with `watch`, `sweep`, `undo`, `migrate`, and `tray` subcommands. Calls `config.load_overrides()` after `db.init_db()` to apply saved settings.
- **setup.ps1** — registers two Task Scheduler tasks: `FileSorter-Watch` (on logon, launches tray mode) and `FileSorter-Sweep` (daily at 2 AM).

## Key design decisions

- Extension → category mapping is the single source of truth in `config.py`. Unrecognized extensions are left in place.
- SQLite (`fileSorter.db`) is the single source of truth for move history. Log files are kept as a human-readable audit trail but are not parsed at runtime.
- Undo marks moves as `undone=1` in the database — full history is preserved.
- Duplicate resolution appends ` (1)`, ` (2)`, etc. — never overwrites.
- The watcher uses a per-file debounce timer (default 3s) so that Chrome `.crdownload` → final rename events are handled cleanly.
- `recursive=False` on the observer — only top-level files are watched, not the category subfolders.
- Priority order for sorting: temp file → dotfile → ignore list → client match → regex rules → extension category.
