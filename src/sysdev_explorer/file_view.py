"""Central file listing widget: grid (icon) view and list (detail) view."""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk  # noqa: E402

from sysdev_explorer import fileops, icons
from sysdev_explorer.disk_utils import human_size

COL_NAME, COL_PATH, COL_PIXBUF, COL_MARKUP, COL_IS_DIR, COL_SIZE, COL_MTIME, COL_TYPE = range(8)

_uri_targets = Gtk.TargetList.new([])
_uri_targets.add_uri_targets(0)


class FileView(Gtk.Box):
    __gsignals__ = {
        "path-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "status-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "open-terminal-request": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "file-opened": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, clipboard_state, start_path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.clipboard_state = clipboard_state
        self.current_path = start_path
        self.history = [start_path]
        self.history_index = 0
        self._search_text = ""

        self.store = Gtk.ListStore(str, str, GdkPixbuf.Pixbuf, str, bool, GObject.TYPE_INT64, float, str)
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._filter_func)

        self.icon_view = Gtk.IconView(model=self.filter_model)
        self.icon_view.set_pixbuf_column(COL_PIXBUF)
        self.icon_view.set_markup_column(COL_MARKUP)
        self.icon_view.set_item_width(110)
        self.icon_view.set_column_spacing(6)
        self.icon_view.set_row_spacing(10)
        self.icon_view.get_style_context().add_class("file-grid")
        self.icon_view.connect("item-activated", self._on_icon_activated)
        self.icon_view.connect("selection-changed", lambda _v: self.emit("selection-changed"))
        self.icon_view.connect("button-press-event", self._on_button_press)

        self.list_store_sorted = Gtk.TreeModelSort(model=self.filter_model)
        self.tree_view = Gtk.TreeView(model=self.list_store_sorted)
        self.tree_view.get_style_context().add_class("file-list")
        self._build_tree_columns()
        self.tree_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tree_view.connect("row-activated", self._on_row_activated)
        self.tree_view.get_selection().connect("changed", lambda _s: self.emit("selection-changed"))
        self.tree_view.connect("button-press-event", self._on_button_press)

        self.stack = Gtk.Stack()
        self.stack.add_named(self._wrap_scroller(self.icon_view), "grid")
        self.stack.add_named(self._wrap_scroller(self.tree_view), "list")
        self.stack.set_visible_child_name("grid")
        self.pack_start(self.stack, True, True, 0)

        self._enable_drag_and_drop()
        self.refresh()

    # -- setup helpers ---------------------------------------------------
    def _wrap_scroller(self, widget):
        scroller = Gtk.ScrolledWindow()
        scroller.add(widget)
        return scroller

    def _build_tree_columns(self):
        name_col = Gtk.TreeViewColumn("Ad")
        name_col.set_expand(True)
        name_col.set_resizable(True)
        icon_renderer = Gtk.CellRendererPixbuf()
        name_col.pack_start(icon_renderer, False)
        name_col.add_attribute(icon_renderer, "pixbuf", COL_PIXBUF)
        text_renderer = Gtk.CellRendererText()
        name_col.pack_start(text_renderer, True)
        name_col.add_attribute(text_renderer, "text", COL_NAME)
        name_col.set_sort_column_id(COL_NAME)
        self.tree_view.append_column(name_col)

        size_renderer = Gtk.CellRendererText(xalign=1.0)
        size_col = Gtk.TreeViewColumn("Boyut", size_renderer)
        size_col.set_cell_data_func(size_renderer, self._render_size)
        size_col.set_resizable(True)
        size_col.set_sort_column_id(COL_SIZE)
        self.tree_view.append_column(size_col)

        type_col = Gtk.TreeViewColumn("Tür", Gtk.CellRendererText(), text=COL_TYPE)
        type_col.set_resizable(True)
        self.tree_view.append_column(type_col)

        mtime_renderer = Gtk.CellRendererText()
        mtime_col = Gtk.TreeViewColumn("Değiştirilme", mtime_renderer)
        mtime_col.set_cell_data_func(mtime_renderer, self._render_mtime)
        mtime_col.set_resizable(True)
        mtime_col.set_sort_column_id(COL_MTIME)
        self.tree_view.append_column(mtime_col)

    def _render_size(self, _col, cell, model, tree_iter, _data=None):
        is_dir = model.get_value(tree_iter, COL_IS_DIR)
        size = model.get_value(tree_iter, COL_SIZE)
        cell.set_property("text", "-" if is_dir else human_size(size))

    def _render_mtime(self, _col, cell, model, tree_iter, _data=None):
        mtime = model.get_value(tree_iter, COL_MTIME)
        cell.set_property("text", fileops.format_mtime(mtime))

    # -- loading -----------------------------------------------------------
    def refresh(self):
        self.load_directory(self.current_path, push_history=False)

    def load_directory(self, path, push_history=True):
        if path.startswith("trash://") or path.startswith("network://"):
            self.store.clear()
            self.emit("status-changed", "Bu konum henüz desteklenmiyor")
            self.current_path = path
            self.emit("path-changed", path)
            return
        try:
            entries = list(os.scandir(path))
        except OSError as exc:
            self.emit("status-changed", f"Klasör okunamadı: {exc}")
            return

        self.store.clear()
        entries.sort(key=lambda e: (not e.is_dir(follow_symlinks=True), e.name.lower()))

        n_dirs = n_files = 0
        total_size = 0
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            is_dir = entry.is_dir(follow_symlinks=True)
            pixbuf = icons.pixbuf_for_path(entry.path, size=48)
            if is_dir:
                n_dirs += 1
                try:
                    n_children = len(os.listdir(entry.path))
                except OSError:
                    n_children = 0
                subtitle = f"{n_children} öge"
                type_label = "Klasör"
                size_bytes = 0
            else:
                n_files += 1
                total_size += st.st_size
                subtitle = human_size(st.st_size)
                type_label = fileops.guess_type_label(entry.path)
                size_bytes = st.st_size

            name = GLib.markup_escape_text(entry.name)
            markup = f"{name}\n<small>{GLib.markup_escape_text(subtitle)}</small>"
            self.store.append([
                entry.name, entry.path, pixbuf, markup, is_dir, size_bytes, st.st_mtime, type_label,
            ])

        self.current_path = path
        if push_history:
            self.history = self.history[: self.history_index + 1]
            self.history.append(path)
            self.history_index = len(self.history) - 1

        self.emit("path-changed", path)
        self.emit("status-changed", f"{n_dirs} klasör, {n_files} dosya (Toplam {human_size(total_size)})")

    # -- navigation ----------------------------------------------------
    def can_go_back(self):
        return self.history_index > 0

    def can_go_forward(self):
        return self.history_index < len(self.history) - 1

    def go_back(self):
        if self.can_go_back():
            self.history_index -= 1
            self.load_directory(self.history[self.history_index], push_history=False)

    def go_forward(self):
        if self.can_go_forward():
            self.history_index += 1
            self.load_directory(self.history[self.history_index], push_history=False)

    def go_up(self):
        parent = os.path.dirname(self.current_path.rstrip("/"))
        if parent and parent != self.current_path:
            self.load_directory(parent or "/")

    def navigate(self, path):
        self.load_directory(path)

    # -- view mode -------------------------------------------------------
    def set_view_mode(self, mode):
        self.stack.set_visible_child_name(mode)

    # -- selection ---------------------------------------------------------
    def get_selected_paths(self):
        if self.stack.get_visible_child_name() == "grid":
            paths = []
            for tree_path in self.icon_view.get_selected_items():
                it = self.filter_model.get_iter(tree_path)
                paths.append(self.filter_model.get_value(it, COL_PATH))
            return paths
        model, rows = self.tree_view.get_selection().get_selected_rows()
        return [model.get_value(model.get_iter(p), COL_PATH) for p in rows]

    def get_selected_infos(self):
        paths = self.get_selected_paths()
        return [(p, os.path.isdir(p)) for p in paths]

    # -- filtering ---------------------------------------------------------
    def set_search_text(self, text):
        self._search_text = text.lower()
        self.filter_model.refilter()

    def _filter_func(self, model, tree_iter, _data=None):
        if not self._search_text:
            return True
        name = model.get_value(tree_iter, COL_NAME) or ""
        return self._search_text in name.lower()

    # -- activation / open -------------------------------------------------
    def _on_icon_activated(self, _view, tree_path):
        it = self.filter_model.get_iter(tree_path)
        self._activate_row(self.filter_model, it)

    def _on_row_activated(self, _view, tree_path, _col):
        it = self.list_store_sorted.get_iter(tree_path)
        self._activate_row(self.list_store_sorted, it)

    def _activate_row(self, model, it):
        path = model.get_value(it, COL_PATH)
        is_dir = model.get_value(it, COL_IS_DIR)
        if is_dir:
            self.navigate(path)
        else:
            fileops.open_with_default_app(path)
            self.emit("file-opened", path)

    def open_selected(self):
        for path, is_dir in self.get_selected_infos():
            if is_dir:
                self.navigate(path)
            else:
                fileops.open_with_default_app(path)
                self.emit("file-opened", path)

    # -- context menu --------------------------------------------------
    def _on_button_press(self, widget, event):
        if event.button != 3:
            return False
        if widget is self.icon_view:
            item = widget.get_path_at_pos(int(event.x), int(event.y))
            if item is not None and not widget.path_is_selected(item):
                widget.unselect_all()
                widget.select_path(item)
        else:
            path_info = widget.get_path_at_pos(int(event.x), int(event.y))
            if path_info:
                tpath = path_info[0]
                sel = widget.get_selection()
                if not sel.path_is_selected(tpath):
                    sel.unselect_all()
                    sel.select_path(tpath)
        self._show_context_menu(event)
        return True

    def _show_context_menu(self, event):
        selected = self.get_selected_infos()
        menu = Gtk.Menu()

        def item(label, sensitive=True):
            mi = Gtk.MenuItem(label=label)
            mi.set_sensitive(sensitive)
            menu.append(mi)
            return mi

        if selected:
            item("Aç").connect("activate", lambda _m: self.open_selected())
            if len(selected) == 1 and selected[0][1]:
                item("Terminal ile Aç").connect(
                    "activate", lambda _m: self.emit("open-terminal-request", selected[0][0])
                )
            menu.append(Gtk.SeparatorMenuItem())
            item("Kopyala").connect("activate", lambda _m: self.copy_selected())
            item("Kes").connect("activate", lambda _m: self.cut_selected())
        item("Yapıştır", sensitive=self.clipboard_state.has_content).connect(
            "activate", lambda _m: self.paste()
        )
        menu.append(Gtk.SeparatorMenuItem())
        if selected:
            item("Yeniden Adlandır", sensitive=len(selected) == 1).connect(
                "activate", lambda _m: self.rename_selected()
            )
            item("Sil").connect("activate", lambda _m: self.delete_selected())
            menu.append(Gtk.SeparatorMenuItem())
            item("Özellikler").connect("activate", lambda _m: self.emit("selection-changed"))
        item("Terminal Aç Burada").connect(
            "activate", lambda _m: self.emit("open-terminal-request", self.current_path)
        )
        menu.show_all()
        menu.popup_at_pointer(event)

    # -- operations ----------------------------------------------------
    def new_folder(self):
        path = fileops.create_folder(self.current_path)
        self.refresh()
        self.select_by_path(path)

    def new_file(self):
        path = fileops.create_file(self.current_path)
        self.refresh()
        self.select_by_path(path)

    def copy_selected(self):
        paths = self.get_selected_paths()
        if paths:
            self.clipboard_state.set(paths, is_cut=False)

    def cut_selected(self):
        paths = self.get_selected_paths()
        if paths:
            self.clipboard_state.set(paths, is_cut=True)

    def paste(self):
        if not self.clipboard_state.has_content:
            return
        if self.clipboard_state.is_cut:
            fileops.move_paths(self.clipboard_state.paths, self.current_path)
            self.clipboard_state.clear()
        else:
            fileops.copy_paths(self.clipboard_state.paths, self.current_path)
        self.refresh()

    def delete_selected(self):
        paths = self.get_selected_paths()
        if not paths:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"{len(paths)} öge çöp kutusuna taşınsın mı?",
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            fileops.trash_paths(paths)
            self.refresh()

    def rename_selected(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            return
        old_path = paths[0]
        old_name = os.path.basename(old_path.rstrip("/"))
        dialog = Gtk.Dialog(
            title="Yeniden Adlandır",
            transient_for=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.add_buttons(
            "İptal", Gtk.ResponseType.CANCEL, "Yeniden Adlandır", Gtk.ResponseType.OK
        )
        entry = Gtk.Entry(text=old_name)
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(10)
        box.add(entry)
        entry.show()
        if dialog.run() == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name and new_name != old_name:
                try:
                    fileops.rename_path(old_path, new_name)
                except OSError as exc:
                    self.emit("status-changed", f"Yeniden adlandırılamadı: {exc}")
                self.refresh()
        dialog.destroy()

    def select_by_path(self, path):
        for row in self.store:
            if row[COL_PATH] == path:
                if self.stack.get_visible_child_name() == "grid":
                    filter_path = self.filter_model.convert_child_path_to_path(row.path)
                    if filter_path:
                        self.icon_view.select_path(filter_path)
                        self.icon_view.scroll_to_path(filter_path, False, 0, 0)
                break

    # -- drag and drop -------------------------------------------------
    def _enable_drag_and_drop(self):
        for widget in (self.icon_view, self.tree_view):
            widget.drag_source_set(
                Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY | Gdk.DragAction.MOVE
            )
            widget.drag_source_set_target_list(_uri_targets)
            widget.connect("drag-data-get", self._on_drag_data_get)

            widget.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
            widget.drag_dest_set_target_list(_uri_targets)
            widget.connect("drag-data-received", self._on_drag_data_received)

    def _on_drag_data_get(self, _widget, _ctx, data, _info, _time):
        uris = [GLib.filename_to_uri(p) for p in self.get_selected_paths()]
        data.set_uris(uris)

    def _on_drag_data_received(self, _widget, _ctx, _x, _y, data, _info, _time):
        uris = data.get_uris()
        paths = []
        for uri in uris:
            try:
                path, _frag = GLib.filename_from_uri(uri)
                paths.append(path)
            except GLib.Error:
                continue
        if paths:
            fileops.copy_paths(paths, self.current_path)
            self.refresh()
