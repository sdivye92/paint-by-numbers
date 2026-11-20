"""Native "choose a folder" dialog for the local Streamlit app.

Streamlit runs in a browser, which cannot reveal a real folder path, so when the app runs on
your own machine we open the OS dialog from the server process instead. Tries tkinter (in a
subprocess so it can't disturb Streamlit's threads), then zenity, then kdialog.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

_TK_SCRIPT = (
    "import sys, tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "print(filedialog.askdirectory(initialdir=sys.argv[1], title='Choose export folder') or '')\n"
)


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def pick_folder(initial: str = "~") -> str | None:
    """Return the chosen folder, or None if cancelled / no dialog is available."""
    from pathlib import Path

    start = str(Path(initial).expanduser())
    if not Path(start).is_dir():
        start = str(Path.home())

    attempts = [[sys.executable, "-c", _TK_SCRIPT, start]]
    if shutil.which("zenity"):
        attempts.append(["zenity", "--file-selection", "--directory", f"--filename={start}/", "--title=Choose export folder"])
    if shutil.which("kdialog"):
        attempts.append(["kdialog", "--getexistingdirectory", start])
    for cmd in attempts:
        choice = _run(cmd)
        if choice:
            return choice
    return None
