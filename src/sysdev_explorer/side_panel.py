"""Right-hand panel: Genel / İzinler / Paylaşım tabs, Git Durumu, Önizleme."""
import grp
import os
import pwd

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from sysdev_explorer import fileops, git_utils, icons
from sysdev_explorer.disk_utils import human_size

PERM_ROWS = [
    ("Sahip", "owner_r", "owner_w", "owner_x"),
    ("Grup", "group_r", "group_w", "group_x"),
    ("Diğer", "other_r", "other_w", "other_x"),
]


class SidePanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_size_request(300, -1)
        self.get_style_context().add_class("side-panel")
        self._current_path = None

        self._build_properties_box()
        self._build_git_box()
        self._build_preview_box()

        self.show_all()
        self.git_frame.set_visible(False)
        self.preview_frame.set_visible(False)

    # -- Genel / İzinler / Paylaşım --------------------------------------
    def _build_properties_box(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("panel-frame")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(10)

        header = Gtk.Label(xalign=0)
        header.get_style_context().add_class("panel-title")
        self.title_label = header
        outer.pack_start(header, False, False, 0)

        self.icon_image = Gtk.Image()
        self.icon_image.set_halign(Gtk.Align.CENTER)
        outer.pack_start(self.icon_image, False, False, 4)

        self.notebook = Gtk.Notebook()
        outer.pack_start(self.notebook, True, True, 0)

        self.notebook.append_page(self._build_general_tab(), Gtk.Label(label="Genel"))
        self.notebook.append_page(self._build_permissions_tab(), Gtk.Label(label="İzinler"))
        self.notebook.append_page(self._build_sharing_tab(), Gtk.Label(label="Paylaşım"))

        frame.add(outer)
        self.pack_start(frame, False, False, 0)

    def _build_general_tab(self):
        grid = Gtk.Grid(row_spacing=6, column_spacing=10)
        grid.set_border_width(8)
        self.general_labels = {}
        rows = ["Tür", "Konum", "Boyut", "İçerik", "Oluşturulma", "Değiştirilme"]
        for i, key in enumerate(rows):
            k = Gtk.Label(label=f"{key}:", xalign=0)
            k.get_style_context().add_class("dim-label")
            v = Gtk.Label(xalign=0, wrap=True)
            v.set_max_width_chars(28)
            grid.attach(k, 0, i, 1, 1)
            grid.attach(v, 1, i, 1, 1)
            self.general_labels[key] = v
        return grid

    def _build_permissions_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(8)

        self.owner_label = Gtk.Label(xalign=0)
        box.pack_start(self.owner_label, False, False, 0)

        grid = Gtk.Grid(row_spacing=4, column_spacing=12)
        grid.attach(Gtk.Label(label=""), 0, 0, 1, 1)
        grid.attach(Gtk.Label(label="Okuma"), 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Yazma"), 2, 0, 1, 1)
        grid.attach(Gtk.Label(label="Çalıştırma"), 3, 0, 1, 1)

        self.perm_checks = {}
        for row_i, (label, rk, wk, xk) in enumerate(PERM_ROWS, start=1):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row_i, 1, 1)
            for col_i, key in enumerate((rk, wk, xk), start=1):
                cb = Gtk.CheckButton()
                cb.connect("toggled", self._on_permission_toggled, key)
                grid.attach(cb, col_i, row_i, 1, 1)
                self.perm_checks[key] = cb
        box.pack_start(grid, False, False, 0)

        self.perm_octal_label = Gtk.Label(xalign=0)
        self.perm_octal_label.get_style_context().add_class("dim-label")
        box.pack_start(self.perm_octal_label, False, False, 4)
        return box

    def _build_sharing_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(8)
        info = Gtk.Label(
            label="Yerel ağda paylaşım için Samba/NFS servisleri gerekir.",
            xalign=0, wrap=True,
        )
        info.get_style_context().add_class("dim-label")
        box.pack_start(info, False, False, 0)

        self.share_path_entry = Gtk.Entry(editable=False)
        box.pack_start(self.share_path_entry, False, False, 0)

        copy_btn = Gtk.Button(label="Konum Yolunu Kopyala")
        copy_btn.connect("clicked", self._on_copy_path)
        box.pack_start(copy_btn, False, False, 0)
        return box

    def _on_copy_path(self, _btn):
        if self._current_path:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self._current_path, -1)

    def _on_permission_toggled(self, checkbutton, key):
        if not self._current_path or getattr(self, "_updating_perms", False):
            return
        try:
            fileops.set_permission_bit(self._current_path, key, checkbutton.get_active())
        except OSError:
            pass
        self._refresh_permissions_display()

    # -- Git Durumu -----------------------------------------------------
    def _build_git_box(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("panel-frame")
        self.git_frame = frame
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(10)
        title = Gtk.Label(label="Git Durumu", xalign=0)
        title.get_style_context().add_class("panel-title")
        box.pack_start(title, False, False, 0)

        self.git_branch_label = Gtk.Label(xalign=0)
        box.pack_start(self.git_branch_label, False, False, 0)
        self.git_commit_label = Gtk.Label(xalign=0)
        self.git_commit_label.get_style_context().add_class("dim-label")
        box.pack_start(self.git_commit_label, False, False, 0)

        self.git_changes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(self.git_changes_box, False, False, 4)

        frame.add(box)
        self.pack_start(frame, False, False, 0)

    # -- Önizleme ---------------------------------------------------------
    def _build_preview_box(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("panel-frame")
        self.preview_frame = frame
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label(label="Önizleme", xalign=0)
        title.get_style_context().add_class("panel-title")
        header.pack_start(title, True, True, 0)
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", lambda _b: self.preview_frame.set_visible(False))
        header.pack_end(close_btn, False, False, 0)
        box.pack_start(header, False, False, 0)

        self.preview_image = Gtk.Image()
        box.pack_start(self.preview_image, True, True, 0)
        self.preview_text = Gtk.Label(wrap=True, xalign=0)
        box.pack_start(self.preview_text, True, True, 0)

        frame.add(box)
        self.pack_start(frame, True, True, 0)

    # -- public API ----------------------------------------------------
    def update_selection(self, path):
        self._current_path = path
        self._updating_perms = True
        if not path or not os.path.exists(path):
            self.title_label.set_markup("<b>Seçim yok</b>")
            self.icon_image.clear()
            self.git_frame.set_visible(False)
            self.preview_frame.set_visible(False)
            self._updating_perms = False
            return

        name = os.path.basename(path.rstrip("/")) or path
        self.title_label.set_markup(f"<b>{name}</b>")
        self.icon_image.set_from_pixbuf(icons.pixbuf_for_path(path, size=64))

        is_dir = os.path.isdir(path)
        try:
            st = os.stat(path)
        except OSError:
            st = None

        self.general_labels["Tür"].set_text(fileops.guess_type_label(path))
        self.general_labels["Konum"].set_text(os.path.dirname(path) or "/")
        self.general_labels["Boyut"].set_text(human_size(st.st_size) if st and not is_dir else "-")
        self.general_labels["İçerik"].set_text("Hesaplanıyor..." if is_dir else "-")
        self.general_labels["Oluşturulma"].set_text(fileops.format_mtime(getattr(st, "st_ctime", None)) if st else "-")
        self.general_labels["Değiştirilme"].set_text(fileops.format_mtime(getattr(st, "st_mtime", None)) if st else "-")

        if is_dir:
            fileops.dir_summary_async(path, self._on_dir_summary_ready)

        self.share_path_entry.set_text(path)
        self._refresh_permissions_display()
        self._refresh_git_status(path if is_dir else os.path.dirname(path))
        self._refresh_preview(path, is_dir)
        self._updating_perms = False

    def _on_dir_summary_ready(self, n_dirs, n_files, total_size):
        self.general_labels["İçerik"].set_text(f"{n_dirs} klasör, {n_files} dosya")
        return False

    def _refresh_permissions_display(self):
        if not self._current_path:
            return
        self._updating_perms = True
        try:
            st = os.stat(self._current_path)
        except OSError:
            self._updating_perms = False
            return
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)
        self.owner_label.set_markup(f"<b>{owner}</b>:{group}")

        bits = fileops.permission_bits(st.st_mode)
        for key, cb in self.perm_checks.items():
            cb.set_active(bits[key])
        self.perm_octal_label.set_text(fileops.permissions_string(st.st_mode))
        self._updating_perms = False

    def _refresh_git_status(self, dir_path):
        status = git_utils.repo_status(dir_path) if dir_path else None
        if not status:
            self.git_frame.set_visible(False)
            return
        self.git_frame.set_visible(True)
        self.git_branch_label.set_markup(f"🌿 <b>{status['branch']}</b>")
        self.git_commit_label.set_text(f"Son commit: {status['commit_hash']} ({status['commit_when']})")

        for child in list(self.git_changes_box.get_children()):
            self.git_changes_box.remove(child)

        def add_change_row(text, count):
            if count <= 0:
                return
            row = Gtk.Label(label=f"{text}: {count}", xalign=0)
            self.git_changes_box.pack_start(row, False, False, 0)

        add_change_row("Değişmiş dosyalar", status["modified"])
        add_change_row("Hazırlanan dosyalar", status["staged"])
        add_change_row("İzlenmeyen dosyalar", status["untracked"])
        add_change_row("Silinen dosyalar", status["deleted"])
        if not any(status[k] for k in ("modified", "staged", "untracked", "deleted")):
            self.git_changes_box.pack_start(
                Gtk.Label(label="Çalışma dizini temiz", xalign=0), False, False, 0
            )
        self.git_changes_box.show_all()

    def _refresh_preview(self, path, is_dir):
        if is_dir:
            self.preview_frame.set_visible(False)
            return
        pixbuf = icons.thumbnail_for_image(path)
        if pixbuf:
            self.preview_image.set_from_pixbuf(pixbuf)
            self.preview_image.set_visible(True)
            self.preview_text.set_visible(False)
            self.preview_frame.set_visible(True)
            return

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                snippet = fh.read(600)
            if snippet.strip():
                self.preview_image.set_visible(False)
                self.preview_text.set_visible(True)
                self.preview_text.set_text(snippet)
                self.preview_frame.set_visible(True)
                return
        except (OSError, UnicodeDecodeError):
            pass
        self.preview_frame.set_visible(False)
