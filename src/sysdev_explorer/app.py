"""GTK Application bootstrap for SysDev Explorer."""
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "com.sysdev.explorer"


def _load_css():
    from sysdev_explorer.preferences import Preferences
    if Preferences().get("theme") == "system":
        return

    css_path = os.environ.get("SYSDEV_EXPLORER_CSS")
    if not css_path:
        # app.py lives in <project_root>/src/sysdev_explorer/app.py
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        css_path = os.path.join(project_root, "data", "style.css")
    if not os.path.exists(css_path):
        return
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(css_path)
    except Exception:
        return
    from gi.repository import Gdk
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_screen(
            display.get_default_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


class SysDevExplorerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        _load_css()

    def do_activate(self):
        from sysdev_explorer.window import MainWindow
        if not self.window:
            self.window = MainWindow(self)
        self.window.present()

    def do_open(self, files, _n_files, _hint):
        self.do_activate()
        if files:
            path = files[0].get_path()
            if path and os.path.isdir(path):
                self.window.open_tab(path)
            elif path:
                self.window.open_tab(os.path.dirname(path))


def main():
    app = SysDevExplorerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
