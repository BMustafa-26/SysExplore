"""Persisted user preferences (hidden files, default view mode, theme)."""
import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "sysdev-explorer")
PREFS_FILE = os.path.join(CONFIG_DIR, "preferences.json")

DEFAULTS = {
    "show_hidden": False,
    "view_mode": "grid",
    "theme": "dark",
}


class Preferences:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(PREFS_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()
