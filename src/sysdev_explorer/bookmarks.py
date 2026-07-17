"""Persisted sidebar shortcuts (drag a folder onto the sidebar to add one)."""
import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "sysdev-explorer")
BOOKMARKS_FILE = os.path.join(CONFIG_DIR, "bookmarks.json")


def load():
    try:
        with open(BOOKMARKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except (OSError, ValueError):
        pass
    return []


def save(bookmarks):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as fh:
        json.dump(bookmarks, fh, ensure_ascii=False, indent=2)


def add(path):
    bookmarks = load()
    if any(b["path"] == path for b in bookmarks):
        return bookmarks
    bookmarks.append({"name": os.path.basename(path.rstrip("/")) or path, "path": path})
    save(bookmarks)
    return bookmarks


def remove(path):
    bookmarks = [b for b in load() if b["path"] != path]
    save(bookmarks)
    return bookmarks
