"""Left sidebar: quick locations, mounted disks, network, user shortcuts."""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

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

        self._disk_bars = {}
        self.volume_monitor = Gio.VolumeMonitor.get()
        self.volume_monitor.connect("volume-added", lambda *_a: self._rebuild())
        self.volume_monitor.connect("volume-removed", lambda *_a: self._rebuild())
        self.volume_monitor.connect("mount-added", lambda *_a: self._rebuild())
        self.volume_monitor.connect("mount-removed", lambda *_a: self._rebuild())

        self._build_all()
        self._enable_drop_target()
        GLib.timeout_add_seconds(15, self._refresh_disks)

    def _build_all(self):
        self._add_header("Konumlar")
        for icon_name, label, path in LOCATIONS:
            self._add_location_row(icon_name, label, path)

        self._add_header("Diskler")
        self._disk_bars = {}
        for disk in list_disks():
            self._add_disk_row(disk)
        self._add_removable_volumes()

        self._add_header("Ağ")
        self._add_location_row("network-workgroup-symbolic", "Ağ Konumları", "network:///")
        self._add_action_row("network-transmit-receive-symbolic", "Bağlan...", self._on_connect_clicked)

        self._add_header("Kısayollar")
        for bm in bookmarks.load():
            row = self._add_location_row("folder-symbolic", bm["name"], bm["path"], removable=True)
            row.is_bookmark = True

    def _rebuild(self):
        for child in list(self.list_box.get_children()):
            self.list_box.remove(child)
        self._build_all()

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

    # -- removable volumes (USB etc.) --------------------------------------
    def _add_removable_volumes(self):
        mounted_paths = {disk["mount_point"] for disk in list_disks()}
        for volume in self.volume_monitor.get_volumes():
            drive = volume.get_drive()
            is_removable = bool(drive) and (drive.is_removable() or drive.is_media_removable())
            if not is_removable:
                continue
            mount = volume.get_mount()
            if mount and mount.get_root().get_path() in mounted_paths:
                continue  # already listed as a regular mounted disk above
            self._add_volume_row(volume, mount)

    def _add_volume_row(self, volume, mount):
        row = Gtk.ListBoxRow()
        row.path = mount.get_root().get_path() if mount else None
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_border_width(4)
        image = Gtk.Image.new_from_icon_name("drive-removable-media-symbolic", Gtk.IconSize.MENU)
        box.pack_start(image, False, False, 0)
        label = Gtk.Label(label=volume.get_name(), xalign=0)
        box.pack_start(label, True, True, 0)

        if mount:
            btn = Gtk.Button.new_from_icon_name("media-eject-symbolic", Gtk.IconSize.MENU)
            btn.set_tooltip_text("Çıkar")
            btn.connect("clicked", lambda _b: self._eject_volume(volume))
        else:
            btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.MENU)
            btn.set_tooltip_text("Bağla")
            btn.connect("clicked", lambda _b: self._mount_volume(volume))
        btn.set_relief(Gtk.ReliefStyle.NONE)
        box.pack_end(btn, False, False, 0)

        row.add(box)
        self.list_box.add(row)
        row.show_all()

    def _mount_volume(self, volume):
        mount_op = Gtk.MountOperation(parent=self.get_toplevel())

        def on_done(vol, result, _data=None):
            try:
                vol.mount_finish(result)
            except GLib.Error as exc:
                self._show_mount_error(exc.message)
                return
            self._rebuild()

        volume.mount(Gio.MountMountFlags.NONE, mount_op, None, on_done, None)

    def _eject_volume(self, volume):
        mount = volume.get_mount()
        if not mount:
            return

        def on_done(m, result, _data=None):
            try:
                m.unmount_with_operation_finish(result)
            except GLib.Error as exc:
                self._show_mount_error(exc.message)
                return
            self._rebuild()

        mount.unmount_with_operation(Gio.MountUnmountFlags.NONE, None, None, on_done, None)

    # -- bookmarks / drop target --------------------------------------------
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

    # -- network mount -------------------------------------------------
    def _on_connect_clicked(self):
        dialog = Gtk.Dialog(
            title="Ağ Konumuna Bağlan", transient_for=self.get_toplevel(), modal=True,
        )
        dialog.add_buttons("İptal", Gtk.ResponseType.CANCEL, "Bağlan", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(12)
        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        box.add(grid)

        grid.attach(Gtk.Label(label="Adres (smb://, sftp://, ftp://):", xalign=0), 0, 0, 1, 1)
        uri_entry = Gtk.Entry()
        uri_entry.set_placeholder_text("smb://sunucu/paylasim")
        uri_entry.set_activates_default(True)
        grid.attach(uri_entry, 0, 1, 1, 1)
        grid.attach(Gtk.Label(label="Kullanıcı adı (isteğe bağlı):", xalign=0), 0, 2, 1, 1)
        user_entry = Gtk.Entry()
        grid.attach(user_entry, 0, 3, 1, 1)
        grid.attach(Gtk.Label(label="Parola (isteğe bağlı):", xalign=0), 0, 4, 1, 1)
        pass_entry = Gtk.Entry()
        pass_entry.set_visibility(False)
        grid.attach(pass_entry, 0, 5, 1, 1)
        dialog.show_all()

        response = dialog.run()
        uri = uri_entry.get_text().strip()
        username = user_entry.get_text().strip()
        password = pass_entry.get_text()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not uri:
            return
        self._mount_uri(uri, username, password)

    def _mount_uri(self, uri, username, password):
        gfile = Gio.File.new_for_uri(uri)
        mount_op = Gtk.MountOperation(parent=self.get_toplevel())
        if username:
            mount_op.set_username(username)
        if password:
            mount_op.set_password(password)

        def on_done(gf, result, _data=None):
            try:
                gf.mount_enclosing_volume_finish(result)
            except GLib.Error as exc:
                self._show_mount_error(exc.message)
                return
            local_path = gf.get_path()
            if not local_path:
                mount = gf.find_enclosing_mount(None)
                if mount:
                    local_path = mount.get_root().get_path()
            if local_path:
                self.emit("location-selected", local_path)
                self._rebuild()
            else:
                self._show_mount_error(
                    "Bağlantı başarılı ancak bu konum yerel bir dosya yolu olarak "
                    "erişilebilir değil (GVFS FUSE bağlantısı gerekebilir)."
                )

        gfile.mount_enclosing_volume(Gio.MountMountFlags.NONE, mount_op, None, on_done, None)

    def _show_mount_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), flags=0,
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK,
            text="Bağlanılamadı",
        )
        dialog.format_secondary_text(message)
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
