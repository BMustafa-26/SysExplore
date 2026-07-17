"""Left sidebar: quick locations, mounted disks, network, user shortcuts."""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

from sysdev_explorer import bookmarks
from sysdev_explorer.disk_utils import human_size, list_disks

HOME = os.path.expanduser("~")

LOCATIONS = [
    ("go-home-symbolic", "Ana Dizin", HOME),
    ("user-desktop-symbolic", "Masaüstü", os.path.join(HOME, "Desktop")),
    ("folder-documents-symbolic", "Belgeler", os.path.join(HOME, "Documents")),
    ("folder-download-symbolic", "İndirilenler", os.path.join(HOME, "Downloads")),
    ("folder-music-symbolic", "Müzikler", os.path.join(HOME, "Music")),
    ("folder-pictures-symbolic", "Resimler", os.path.join(HOME, "Pictures")),
    ("folder-videos-symbolic", "Videolar", os.path.join(HOME, "Videos")),
    ("user-trash-symbolic", "Çöp Kutusu", "trash:///"),
]

URI_TARGETS = Gtk.TargetList.new([])
URI_TARGETS.add_uri_targets(0)


class Sidebar(Gtk.Box):
    __gsignals__ = {
        "location-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(220, -1)
        self.get_style_context().add_class("sidebar")

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(scroller, True, True, 0)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.get_style_context().add_class("sidebar-list")
        self.list_box.connect("row-activated", self._on_row_activated)
        scroller.add(self.list_box)

        self._active_row = None
        self._disk_bars = {}
        self._bookmark_rows_start = None

        self._add_header("Konumlar")
        for icon_name, label, path in LOCATIONS:
            self._add_location_row(icon_name, label, path)

        self._add_header("Diskler")
        for disk in list_disks():
            self._add_disk_row(disk)

        self._add_header("Ağ")
        self._add_location_row("network-workgroup-symbolic", "Ağ Konumları", "network:///")
        self._add_action_row("network-transmit-receive-symbolic", "Bağlan...", self._on_connect_clicked)

        self._add_header("Kısayollar")
        self._bookmarks_header_index = len(self.list_box.get_children())
        for bm in bookmarks.load():
            self._add_location_row("folder-symbolic", bm["name"], bm["path"], removable=True)

        self._enable_drop_target()

        GLib.timeout_add_seconds(15, self._refresh_disks)

    # -- construction helpers -------------------------------------------------
    def _add_header(self, text):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        row.get_style_context().add_class("sidebar-header")
        label = Gtk.Label(label=text, xalign=0)
        label.get_style_context().add_class("sidebar-header-label")
        row.add(label)
        self.list_box.add(row)

    def _add_location_row(self, icon_name, label_text, path, removable=False):
        row = Gtk.ListBoxRow()
        row.path = path
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_border_width(4)
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        box.pack_start(image, False, False, 0)
        label = Gtk.Label(label=label_text, xalign=0)
        box.pack_start(label, True, True, 0)
        if removable:
            btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("sidebar-remove-btn")
            btn.connect("clicked", self._on_remove_bookmark, path)
            box.pack_end(btn, False, False, 0)
        row.add(box)
        row.get_style_context().add_class("sidebar-row")
        self.list_box.add(row)
        row.show_all()
        return row

    def _add_action_row(self, icon_name, label_text, callback):
        row = Gtk.ListBoxRow(activatable=True)
        row.path = None
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_border_width(4)
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        box.pack_start(image, False, False, 0)
        label = Gtk.Label(label=label_text, xalign=0)
        box.pack_start(label, True, True, 0)
        row.add(box)
        row.connect("activate", lambda *_a: callback())
        self.list_box.add(row)
        row.show_all()

    def _add_disk_row(self, disk):
        row = Gtk.ListBoxRow()
        row.path = disk["mount_point"]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_border_width(4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        image = Gtk.Image.new_from_icon_name("drive-harddisk-symbolic", Gtk.IconSize.MENU)
        top.pack_start(image, False, False, 0)
        label = Gtk.Label(label=disk["label"], xalign=0)
        top.pack_start(label, True, True, 0)
        box.pack_start(top, False, False, 0)

        bar = Gtk.LevelBar()
        bar.set_min_value(0.0)
        bar.set_max_value(1.0)
        bar.set_value(disk["used_fraction"])
        bar.get_style_context().add_class("disk-bar")
        box.pack_start(bar, False, False, 0)

        sub = Gtk.Label(xalign=0)
        sub.set_markup(
            f'<small>{human_size(disk["used"])} / {human_size(disk["total"])}</small>'
        )
        sub.get_style_context().add_class("dim-label")
        box.pack_start(sub, False, False, 0)

        row.add(box)
        self.list_box.add(row)
        row.show_all()
        self._disk_bars[disk["mount_point"]] = (bar, sub)

    def _refresh_disks(self):
        for disk in list_disks():
            widgets = self._disk_bars.get(disk["mount_point"])
            if widgets:
                bar, sub = widgets
                bar.set_value(disk["used_fraction"])
                sub.set_markup(
                    f'<small>{human_size(disk["used"])} / {human_size(disk["total"])}</small>'
                )
        return True

    def _enable_drop_target(self):
        self.list_box.drag_dest_set(
            Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY
        )
        self.list_box.drag_dest_set_target_list(URI_TARGETS)
        self.list_box.connect("drag-data-received", self._on_drag_data_received)

    def _on_drag_data_received(self, _widget, _ctx, _x, _y, data, _info, _time):
        uris = data.get_uris()
        for uri in uris:
            gfile_path = GLib.filename_from_uri(uri)[0] if uri.startswith("file://") else None
            if gfile_path and os.path.isdir(gfile_path):
                bookmarks.add(gfile_path)
        self.reload_bookmarks()

    def reload_bookmarks(self):
        for child in list(self.list_box.get_children()):
            if getattr(child, "is_bookmark", False):
                self.list_box.remove(child)
        for bm in bookmarks.load():
            row = self._add_location_row("folder-symbolic", bm["name"], bm["path"], removable=True)
            row.is_bookmark = True

    def _on_remove_bookmark(self, _btn, path):
        bookmarks.remove(path)
        self.reload_bookmarks()

    def _on_connect_clicked(self):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Ağ konumuna bağlan",
        )
        dialog.format_secondary_text(
            "smb://, ftp:// veya sftp:// adresini adres çubuğuna yazıp Enter'a basabilirsiniz."
        )
        dialog.run()
        dialog.destroy()

    def _on_row_activated(self, _list_box, row):
        path = getattr(row, "path", None)
        if path:
            self.emit("location-selected", path)

    def select_path(self, path):
        for row in self.list_box.get_children():
            if getattr(row, "path", None) == path:
                self.list_box.select_row(row)
                return
