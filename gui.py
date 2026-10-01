"""Tkinter window GUI for fileSorter."""

import logging
import os
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk

from config import DOWNLOADS_FOLDER
from main import DailyLogHandler
from sorter import _load_history, sweep, undo
from watcher import DownloadHandler

log = logging.getLogger("fileSorter")

BG = "#f8fafc"
CARD = "#ffffff"
PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
SUCCESS = "#16a34a"
WARNING = "#ea580c"
DANGER = "#dc2626"
TEXT = "#1e293b"
TEXT_MUTED = "#64748b"
BORDER = "#e2e8f0"


class TextLogHandler(logging.Handler):
    def __init__(self, text_widget: tk.Text):
        super().__init__()
        self._text = text_widget

    def emit(self, record):
        msg = self.format(record)
        self._text.after(0, self._append, msg)

    def _append(self, msg: str):
        self._text.configure(state="normal")
        self._text.insert("end", msg + "\n")
        self._text.see("end")
        self._text.configure(state="disabled")


class FileSorterApp:
    def __init__(self):
        self._watching = False
        self._observer = None

        self.root = tk.Tk()
        self.root.title("fileSorter")
        self.root.geometry("660x520")
        self.root.minsize(560, 420)
        self.root.configure(bg=BG)

        self._style = ttk.Style()
        self._style.theme_use("clam")
        self._configure_styles()
        self._build_ui()
        self._setup_logging()
        self._refresh_history()

    def _configure_styles(self):
        self._style.configure("Card.TFrame", background=CARD)
        self._style.configure(
            "Title.TLabel", background=BG, foreground=TEXT,
            font=("Segoe UI", 16, "bold"),
        )
        self._style.configure(
            "Subtitle.TLabel", background=BG, foreground=TEXT_MUTED,
            font=("Segoe UI", 9),
        )
        self._style.configure(
            "Status.TLabel", background=BG, foreground=TEXT_MUTED,
            font=("Segoe UI", 9),
        )
        self._style.configure(
            "CardTitle.TLabel", background=CARD, foreground=TEXT,
            font=("Segoe UI", 10, "bold"),
        )

    def _make_button(self, parent, text, color, command):
        btn = tk.Button(
            parent, text=text, command=command,
            bg=color, fg="white", activebackground=color,
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=16, pady=8,
            borderwidth=0, highlightthickness=0,
        )
        return btn

    def _build_ui(self):
        main = ttk.Frame(self.root, style="Card.TFrame")
        main.configure(style="Card.TFrame")

        pad = ttk.Frame(self.root)
        pad.configure(style="Card.TFrame")
        self.root.configure(bg=BG)

        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=20, pady=16)

        ttk.Label(container, text="fileSorter", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container, text=f"Sorting: {DOWNLOADS_FOLDER}", style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        btn_frame = tk.Frame(container, bg=BG)
        btn_frame.pack(fill="x", pady=(0, 12))

        self._watch_btn = self._make_button(
            btn_frame, "Start Watcher", PRIMARY, self._toggle_watcher,
        )
        self._watch_btn.pack(side="left", padx=(0, 8))

        self._make_button(
            btn_frame, "Sweep Now", SUCCESS, self._sweep,
        ).pack(side="left", padx=(0, 8))

        self._make_button(
            btn_frame, "Undo Last", WARNING, self._undo_last,
        ).pack(side="left", padx=(0, 8))

        self._make_button(
            btn_frame, "Undo All", DANGER, self._undo_all,
        ).pack(side="left", padx=(0, 8))

        link_frame = tk.Frame(container, bg=BG)
        link_frame.pack(fill="x", pady=(0, 12))

        dl_link = tk.Label(
            link_frame, text="Open Downloads", fg=PRIMARY, bg=BG,
            cursor="hand2", font=("Segoe UI", 9, "underline"),
        )
        dl_link.pack(side="left", padx=(0, 16))
        dl_link.bind("<Button-1>", lambda e: os.startfile(str(DOWNLOADS_FOLDER)))

        log_link = tk.Label(
            link_frame, text="Open Logs", fg=PRIMARY, bg=BG,
            cursor="hand2", font=("Segoe UI", 9, "underline"),
        )
        log_link.pack(side="left")
        log_link.bind("<Button-1>", lambda e: self._open_logs())

        history_card = tk.LabelFrame(
            container, text="  Recent Moves  ", bg=CARD, fg=TEXT,
            font=("Segoe UI", 10, "bold"), relief="solid", bd=1,
            highlightbackground=BORDER, highlightthickness=0,
        )
        history_card.pack(fill="both", expand=True, pady=(0, 8))

        self._history_list = tk.Listbox(
            history_card, bg=CARD, fg=TEXT, selectbackground=PRIMARY,
            font=("Consolas", 9), relief="flat", highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(history_card, command=self._history_list.yview)
        self._history_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self._history_list.pack(fill="both", expand=True, padx=8, pady=4)

        log_card = tk.LabelFrame(
            container, text="  Log  ", bg=CARD, fg=TEXT,
            font=("Segoe UI", 10, "bold"), relief="solid", bd=1,
            highlightbackground=BORDER, highlightthickness=0,
        )
        log_card.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            log_card, bg=CARD, fg=TEXT, font=("Consolas", 9),
            relief="flat", height=6, state="disabled",
            highlightthickness=0, borderwidth=0, wrap="word",
        )
        log_scroll = ttk.Scrollbar(log_card, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self._log_text.pack(fill="both", expand=True, padx=8, pady=4)

        self._status = ttk.Label(container, text="Ready", style="Status.TLabel")
        self._status.pack(anchor="w", pady=(8, 0))

    def _setup_logging(self):
        log_dir = Path(__file__).parent / "logs"
        fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

        text_handler = TextLogHandler(self._log_text)
        text_handler.setFormatter(fmt)

        file_handler = DailyLogHandler(log_dir)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )

        logger = logging.getLogger("fileSorter")
        logger.setLevel(logging.INFO)
        logger.addHandler(text_handler)
        logger.addHandler(file_handler)

    def _refresh_history(self):
        self._history_list.delete(0, "end")
        records = _load_history()
        for r in reversed(records[-50:]):
            src = Path(r["src"]).name
            dest = Path(r["dest"])
            try:
                rel = dest.relative_to(DOWNLOADS_FOLDER)
            except ValueError:
                rel = dest
            ts = datetime.fromisoformat(r["time"]).astimezone().strftime("%H:%M:%S")
            self._history_list.insert("end", f"  {ts}  {src}  ->  {rel}")

    def _set_status(self, text: str):
        self._status.configure(text=text)

    def _toggle_watcher(self):
        if self._watching:
            if self._observer:
                self._observer.stop()
            self._watching = False
            self._watch_btn.configure(text="Start Watcher", bg=PRIMARY)
            self._set_status("Watcher stopped")
            log.info("Watcher stopped")
            return

        from watchdog.observers import Observer

        self._observer = Observer()
        self._observer.schedule(
            DownloadHandler(DOWNLOADS_FOLDER), str(DOWNLOADS_FOLDER), recursive=False,
        )
        self._observer.daemon = True
        self._observer.start()
        self._watching = True
        self._watch_btn.configure(text="Stop Watcher", bg=DANGER)
        self._set_status("Watcher running...")
        log.info("Watching %s for new files...", DOWNLOADS_FOLDER)

    def _sweep(self):
        def run():
            count = sweep(DOWNLOADS_FOLDER)
            self.root.after(0, self._set_status, f"Sweep done: {count} file(s)")
            self.root.after(0, self._refresh_history)

        self._set_status("Sweeping...")
        threading.Thread(target=run, daemon=True).start()

    def _undo_last(self):
        undone = undo(1)
        self._refresh_history()
        if undone:
            self._set_status(f"Undone {undone} file(s)")
        else:
            self._set_status("Nothing to undo")

    def _undo_all(self):
        total = len(_load_history())
        undone = undo(total)
        self._refresh_history()
        if undone:
            self._set_status(f"Undone {undone} file(s)")
        else:
            self._set_status("Nothing to undo")

    def _open_logs(self):
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(log_dir))

    def run(self):
        self.root.mainloop()


def main():
    app = FileSorterApp()
    app.run()


if __name__ == "__main__":
    main()
