"""Bottom row: embedded terminal, quick actions, recently used files."""
import os
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, GObject, Gtk  # noqa: E402

from sysdev_explorer import fileops, icons

try:
    gi.require_version("Vte", "2.91")
    from gi.repository import Vte
    HAVE_VTE = True
except (ImportError, ValueError):
    Vte = None
    HAVE_VTE = False


class TerminalPanel(Gtk.Box):
    __gsignals__ = {"path-hint-request": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class("panel-frame")
        self._get_cwd = lambda: os.path.expanduser("~")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_border_width(6)
        title = Gtk.Label(label="Terminal", xalign=0)
        title.get_style_context().add_class("panel-title")
        header.pack_start(title, True, True, 0)

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.MENU)
        add_btn.set_relief(Gtk.ReliefStyle.NONE)
        add_btn.set_tooltip_text("Yeni Sekme")
        add_btn.connect("clicked", lambda _b: self.open_tab())
        header.pack_end(add_btn, False, False, 0)
        self.pack_start(header, False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.pack_start(self.notebook, True, True, 0)

        if not HAVE_VTE:
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            info.set_border_width(12)
            label = Gtk.Label(
                wrap=True,
                label=(
                    "Gömülü terminal için VTE kitaplığı bulunamadı "
                    "(gir1.2-vte-2.91). Sistem terminalini açabilirsiniz."
                ),
            )
            info.pack_start(label, False, False, 0)
            open_btn = Gtk.Button(label="Sistem Terminalini Aç")
            open_btn.connect("clicked", lambda _b: fileops.open_terminal_here(self._get_cwd()))
            info.pack_start(open_btn, False, False, 0)
            self.notebook.append_page(info, Gtk.Label(label="Terminal"))
        else:
            self.open_tab()

    def set_cwd_getter(self, func):
        self._get_cwd = func

    def open_tab(self, path=None):
        if not HAVE_VTE:
            fileops.open_terminal_here(path or self._get_cwd())
            return
        cwd = path or self._get_cwd()
        terminal = Vte.Terminal()
        shell = os.environ.get("SHELL", "/bin/bash")
        try:
            terminal.spawn_async(
                Vte.PtyFlags.DEFAULT,
                cwd,
                [shell],
                [],
                GLib.SpawnFlags.SEARCH_PATH,
                None,
                None,
                -1,
                None,
                None,
            )
        except (GLib.Error, TypeError):
            pass
        terminal.set_color_background(_rgba(0.09, 0.09, 0.12, 1.0))
        terminal.set_color_foreground(_rgba(0.85, 0.87, 0.92, 1.0))

        scroller = Gtk.ScrolledWindow()
        scroller.add(terminal)

        tab_label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_label_box.pack_start(Gtk.Label(label=os.path.basename(cwd) or cwd), False, False, 0)
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        tab_label_box.show_all()

        page_index = self.notebook.append_page(scroller, tab_label_box)
        close_btn.connect("clicked", lambda _b: self._close_tab(scroller))
        tab_label_box.pack_start(close_btn, False, False, 0)
        tab_label_box.show_all()
        self.notebook.set_tab_reorderable(scroller, True)
        scroller.show_all()
        self.notebook.set_current_page(page_index)
        terminal.grab_focus()

    def _close_tab(self, scroller):
        page_num = self.notebook.page_num(scroller)
        if page_num != -1:
            if self.notebook.get_n_pages() == 1:
                self.open_tab()
            self.notebook.remove_page(page_num)


def _rgba(r, g, b, a):
    from gi.repository import Gdk
    c = Gdk.RGBA()
    c.red, c.green, c.blue, c.alpha = r, g, b, a
    return c


QUICK_ACTIONS = [
    ("folder-new-symbolic", "Yeni Klasör", "F2", "new_folder"),
    ("document-new-symbolic", "Dosya Oluştur", "Ctrl+N", "new_file"),
    ("edit-symbolic", "Yeniden Adlandır", "F6", "rename"),
    ("edit-copy-symbolic", "Kopyala", "Ctrl+C", "copy"),
    ("edit-cut-symbolic", "Taşı", "Ctrl+X", "cut"),
    ("user-trash-symbolic", "Sil", "Delete", "delete"),
    ("utilities-terminal-symbolic", "Terminal Aç", "Ctrl+T", "terminal"),
    ("document-properties-symbolic", "Özellikler", "Alt+Enter", "properties"),
]


class QuickActionsPanel(Gtk.Box):
    def __init__(self, actions):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_size_request(220, -1)
        self.get_style_context().add_class("panel-frame")
        self.set_border_width(8)

        title = Gtk.Label(label="Hızlı İşlemler", xalign=0)
        title.get_style_context().add_class("panel-title")
        self.pack_start(title, False, False, 0)

        grid = Gtk.Grid(row_spacing=6, column_spacing=6, column_homogeneous=True)
        self.pack_start(grid, False, False, 0)

        for i, (icon_name, label, shortcut, action_key) in enumerate(QUICK_ACTIONS):
            btn = Gtk.Button()
            btn.get_style_context().add_class("quick-action-btn")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.pack_start(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)
            box.pack_start(Gtk.Label(label=label), False, False, 0)
            shortcut_label = Gtk.Label(label=shortcut)
            shortcut_label.get_style_context().add_class("dim-label")
            box.pack_start(shortcut_label, False, False, 0)
            btn.add(box)
            callback = actions.get(action_key)
            if callback:
                btn.connect("clicked", lambda _b, cb=callback: cb())
            grid.attach(btn, i % 2, i // 2, 1, 1)


class RecentPanel(Gtk.Box):
    __gsignals__ = {"file-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.get_style_context().add_class("panel-frame")
        self.set_border_width(8)

        title = Gtk.Label(label="Son Kullanılanlar", xalign=0)
        title.get_style_context().add_class("panel-title")
        self.pack_start(title, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        self.pack_start(scroller, True, True, 0)
        self.list_box = Gtk.ListBox()
        self.list_box.connect("row-activated", self._on_row_activated)
        scroller.add(self.list_box)

        self.recent_manager = Gtk.RecentManager.get_default()
        self.refresh()

    def refresh(self):
        for child in list(self.list_box.get_children()):
            self.list_box.remove(child)

        items = [
            item for item in self.recent_manager.get_items()
            if item.get_uri().startswith("file://") and item.exists()
        ]
        items.sort(key=lambda i: i.get_modified(), reverse=True)

        for item in items[:12]:
            path = GLib.filename_from_uri(item.get_uri())[0]
            row = Gtk.ListBoxRow()
            row.path = path
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_border_width(4)
            box.pack_start(Gtk.Image.new_from_pixbuf(icons.pixbuf_for_path(path, 24)), False, False, 0)

            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            name_label = Gtk.Label(label=os.path.basename(path), xalign=0)
            text_box.pack_start(name_label, False, False, 0)
            path_label = Gtk.Label(label=os.path.dirname(path), xalign=0)
            path_label.get_style_context().add_class("dim-label")
            text_box.pack_start(path_label, False, False, 0)
            box.pack_start(text_box, True, True, 0)

            ago = Gtk.Label(label=_time_ago(item.get_modified()))
            ago.get_style_context().add_class("dim-label")
            box.pack_end(ago, False, False, 0)

            row.add(box)
            self.list_box.add(row)
        self.list_box.show_all()

    def register_opened(self, path):
        self.recent_manager.add_item(Gio.File.new_for_path(path).get_uri())
        self.refresh()

    def _on_row_activated(self, _list_box, row):
        self.emit("file-activated", row.path)


def _time_ago(timestamp):
    delta = max(0, int(time.time()) - int(timestamp))
    if delta < 60:
        return "az önce"
    if delta < 3600:
        return f"{delta // 60} dk önce"
    if delta < 86400:
        return f"{delta // 3600} saat önce"
    return f"{delta // 86400} gün önce"
