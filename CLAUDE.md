# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

fileSorter — a Python utility that automatically organizes files in the Windows Downloads folder into categorized subfolders (Documents, Images, Media, Archives, Installers, Code, Fonts). Supports real-time filesystem watching and one-shot batch sweeps.

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
.venv\Scripts\python main.py watch --log-dir logs

# Tests
.venv\Scripts\python -m pytest test_sorter.py -v    # all tests
.venv\Scripts\python -m pytest test_sorter.py -k "test_client"  # run tests matching keyword

# Background setup (registers Windows Task Scheduler tasks)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## Architecture

- **config.py** — category-to-extensions mapping (`CATEGORIES` dict), reverse lookup (`EXTENSION_MAP`), client keywords (`CLIENTS`), sub-category rules with keyword+extension matching (`CLIENT_SUBCATEGORIES`), temp-file extensions, debounce delay, and default folder path. All tuning happens here.
- **sorter.py** — core logic: `sort_file()` checks client match first (keyword priority over extension for sub-categories), then falls back to extension-based category sorting. `sweep()` iterates the folder. `undo()` reverses moves using `.move_history.jsonl`. Skips temp/dot files and handles locked-file errors.
- **test_sorter.py** — pytest suite (48 tests) covering all sorting functions including undo. Uses `tmp_path` fixtures so tests never touch real files.
- **watcher.py** — `watchdog` filesystem observer. `DownloadHandler` debounces file events (creation + rename) by `DEBOUNCE_SECONDS` before sorting, so in-progress downloads aren't moved prematurely.
- **main.py** — CLI entry point with `watch`, `sweep`, and `undo` subcommands.
- **setup.ps1** — registers two Task Scheduler tasks: `FileSorter-Watch` (on logon, uses `pythonw.exe` for no console) and `FileSorter-Sweep` (daily at 2 AM).

## Key design decisions

- Extension → category mapping is the single source of truth in `config.py`. Unrecognized extensions are left in place.
- Duplicate resolution appends ` (1)`, ` (2)`, etc. — never overwrites.
- The watcher uses a per-file debounce timer (default 3s) so that Chrome `.crdownload` → final rename events are handled cleanly.
- `recursive=False` on the observer — only top-level files are watched, not the category subfolders.
