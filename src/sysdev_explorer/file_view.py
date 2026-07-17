"""Central file listing widget: grid (icon) view and list (detail) view."""
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk  # noqa: E402

from sysdev_explorer import clipboard, fileops, icons, operations
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

    def __init__(self, window, start_path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.current_path = start_path
        self.history = [start_path]
        self.history_index = 0
        self._search_text = ""
        self._load_generation = 0
        self.is_trash = False
        self.show_hidden = window.preferences.get("show_hidden") if window else False

        self.store = Gtk.ListStore(str, str, GdkPixbuf.Pixbuf, str, bool, GObject.TYPE_INT64, float, str)
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._filter_func)

        self.icon_view = Gtk.IconView(model=self.filter_model)
        self.icon_view.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
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
        default_mode = window.preferences.get("view_mode") if window else "grid"
        self.stack.set_visible_child_name(default_mode if default_mode in ("grid", "list") else "grid")
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
        cell.set_property("text", fileops.format_mtime(mtime) if mtime else "-")

    # -- loading -----------------------------------------------------------
    def refresh(self):
        self.load_directory(self.current_path, push_history=False)

    def load_directory(self, path, push_history=True):
        self._load_generation += 1
        if path == "trash:///":
            self._load_trash()
            self._finish_load(path, push_history, status_override=None)
            return
        if path.startswith("network://"):
            self.store.clear()
            self.is_trash = False
            self.emit("status-changed", "Ağ konumları henüz yalnızca 'Bağlan...' ile desteklenir")
            self._finish_load(path, push_history, status_override="")
            return

        self.is_trash = False
        try:
            entries = list(os.scandir(path))
        except OSError as exc:
            self.emit("status-changed", f"Klasör okunamadı: {exc}")
            return

        self.store.clear()
        entries.sort(key=lambda e: (not e.is_dir(follow_symlinks=True), e.name.lower()))

        image_candidates = []
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            is_dir = entry.is_dir(follow_symlinks=True)
            pixbuf = icons.pixbuf_for_path(entry.path, size=48)
            if is_dir:
                try:
                    n_children = len(os.listdir(entry.path))
                except OSError:
                    n_children = 0
                subtitle = f"{n_children} öge"
                type_label = "Klasör"
                size_bytes = 0
            else:
                subtitle = human_size(st.st_size)
                type_label = fileops.guess_type_label(entry.path)
                size_bytes = st.st_size
                if type_label.startswith("image/"):
                    image_candidates.append(entry.path)

            name = GLib.markup_escape_text(entry.name)
            markup = f"{name}\n<small>{GLib.markup_escape_text(subtitle)}</small>"
            self.store.append([
                entry.name, entry.path, pixbuf, markup, is_dir, size_bytes, st.st_mtime, type_label,
            ])

        self._finish_load(path, push_history)
        if image_candidates:
            self._load_thumbnails_async(image_candidates, self._load_generation)

    def _finish_load(self, path, push_history, status_override=None):
        self.current_path = path
        if push_history:
            self.history = self.history[: self.history_index + 1]
            self.history.append(path)
            self.history_index = len(self.history) - 1
        self.emit("path-changed", path)
        if status_override is None:
            self._recompute_status()

    def _recompute_status(self):
        n_dirs = n_files = 0
        total_size = 0
        it = self.filter_model.get_iter_first()
        while it:
            is_dir = self.filter_model.get_value(it, COL_IS_DIR)
            size = self.filter_model.get_value(it, COL_SIZE)
            if is_dir:
                n_dirs += 1
            else:
                n_files += 1
                total_size += size or 0
            it = self.filter_model.iter_next(it)
        if self.is_trash:
            self.emit("status-changed", f"{n_files} öge çöp kutusunda")
        else:
            self.emit("status-changed", f"{n_dirs} klasör, {n_files} dosya (Toplam {human_size(total_size)})")

    # -- thumbnails ------------------------------------------------------
    def _load_thumbnails_async(self, image_paths, generation):
        row_refs = {}
        for row in self.store:
            if row[COL_PATH] in image_paths:
                row_refs[row[COL_PATH]] = Gtk.TreeRowReference.new(self.store, row.path)

        def worker():
            for path in image_paths:
                pixbuf = icons.thumbnail_for_image(path, max_size=48)
                if pixbuf:
                    GLib.idle_add(self._apply_thumbnail, row_refs.get(path), pixbuf, generation)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_thumbnail(self, row_ref, pixbuf, generation):
        if generation != self._load_generation or row_ref is None or not row_ref.valid():
            return False
        tree_path = row_ref.get_path()
        if tree_path is None:
            return False
        it = self.store.get_iter(tree_path)
        self.store.set_value(it, COL_PIXBUF, pixbuf)
        return False

    # -- trash -----------------------------------------------------------
    def _load_trash(self):
        self.store.clear()
        self.is_trash = True
        for item in fileops.list_trash_items():
            pixbuf = icons.named_pixbuf("user-trash", 48) or icons.pixbuf_for_path(item["orig_path"], 48)
            name = GLib.markup_escape_text(item["name"])
            subtitle = human_size(item["size"]) if item["size"] else ""
            markup = f"{name}\n<small>{GLib.markup_escape_text(subtitle)}</small>"
            self.store.append([
                item["name"], item["uri"], pixbuf, markup, False, item["size"] or 0, 0.0, "Çöp",
            ])

    def empty_trash(self):
        uris = [row[COL_PATH] for row in self.store]
        if not uris:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), flags=0,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.YES_NO,
            text=f"{len(uris)} öge kalıcı olarak silinsin mi?",
        )
        dialog.format_secondary_text("Bu işlem geri alınamaz.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            fileops.permanently_delete_trash_items(uris)
            self.refresh()

    def restore_selected(self):
        uris = self.get_selected_paths()
        if not uris:
            return
        operations.run_restore(self.window, uris, lambda result: self._on_restore_done(result))

    def _on_restore_done(self, result):
        if result["errors"]:
            self._show_errors("Geri yüklenemedi", result["errors"])
        self.refresh()

    def permanently_delete_selected(self):
        uris = self.get_selected_paths()
        if not uris:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), flags=0,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.YES_NO,
            text=f"{len(uris)} öge kalıcı olarak silinsin mi?",
        )
        dialog.format_secondary_text("Bu işlem geri alınamaz.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            fileops.permanently_delete_trash_items(uris)
            self.refresh()

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

    # -- view mode / hidden files -----------------------------------------
    def set_view_mode(self, mode):
        self.stack.set_visible_child_name(mode)

    def toggle_hidden_files(self):
        self.show_hidden = not self.show_hidden
        self.filter_model.refilter()
        self._recompute_status()
        return self.show_hidden

    def select_all(self):
        if self.stack.get_visible_child_name() == "grid":
            self.icon_view.select_all()
        else:
            self.tree_view.get_selection().select_all()

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
        self._recompute_status()

    def _filter_func(self, model, tree_iter, _data=None):
        name = model.get_value(tree_iter, COL_NAME) or ""
        if not self.is_trash and not self.show_hidden and name.startswith("."):
            return False
        if not self._search_text:
            return True
        return self._search_text in name.lower()

    # -- activation / open -------------------------------------------------
    def _on_icon_activated(self, _view, tree_path):
        it = self.filter_model.get_iter(tree_path)
        self._activate_row(self.filter_model, it)

    def _on_row_activated(self, _view, tree_path, _col):
        it = self.list_store_sorted.get_iter(tree_path)
        self._activate_row(self.list_store_sorted, it)

    def _activate_row(self, model, it):
        if self.is_trash:
            return
        path = model.get_value(it, COL_PATH)
        is_dir = model.get_value(it, COL_IS_DIR)
        if is_dir:
            self.navigate(path)
        else:
            self._open_path(path)

    def open_selected(self):
        if self.is_trash:
            return
        for path, is_dir in self.get_selected_infos():
            if is_dir:
                self.navigate(path)
            else:
                self._open_path(path)

    def _open_path(self, path):
        if fileops.is_executable_file(path):
            self._confirm_run_executable(path)
            return
        fileops.open_with_default_app(path)
        self.emit("file-opened", path)

    def _confirm_run_executable(self, path):
        name = os.path.basename(path)
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), flags=0,
            message_type=Gtk.MessageType.QUESTION,
            text=f'"{name}" çalıştırılabilir bir dosya',
        )
        dialog.format_secondary_text("Ne yapmak istersiniz?")
        dialog.add_buttons(
            "İptal", Gtk.ResponseType.CANCEL,
            "Görüntüle/Düzenle", 1,
            "Terminalde Çalıştır", 2,
            "Çalıştır", 3,
        )
        response = dialog.run()
        dialog.destroy()
        if response == 1:
            fileops.open_with_default_app(path)
            self.emit("file-opened", path)
        elif response == 2:
            self.emit("open-terminal-request", path)
        elif response == 3:
            fileops.run_executable(path)

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
        if self.is_trash:
            self._show_trash_context_menu(event)
            return

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
            if len(selected) == 1 and not selected[0][1] and fileops.is_archive(selected[0][0]):
                item("Buraya Çıkart").connect("activate", lambda _m: self.extract_selected())
            menu.append(Gtk.SeparatorMenuItem())
            item("Kopyala").connect("activate", lambda _m: self.copy_selected())
            item("Kes").connect("activate", lambda _m: self.cut_selected())
            item("Sıkıştır (zip)").connect("activate", lambda _m: self.compress_selected())
        item("Yapıştır", sensitive=clipboard.has_content()).connect(
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
        item("Gizli Dosyaları Göster" if not self.show_hidden else "Gizli Dosyaları Gizle").connect(
            "activate", lambda _m: self.toggle_hidden_files()
        )
        item("Terminal Aç Burada").connect(
            "activate", lambda _m: self.emit("open-terminal-request", self.current_path)
        )
        menu.show_all()
        menu.popup_at_pointer(event)

    def _show_trash_context_menu(self, event):
        selected = self.get_selected_paths()
        menu = Gtk.Menu()

        def item(label, sensitive=True):
            mi = Gtk.MenuItem(label=label)
            mi.set_sensitive(sensitive)
            menu.append(mi)
            return mi

        item("Geri Yükle", sensitive=bool(selected)).connect("activate", lambda _m: self.restore_selected())
        item("Kalıcı Olarak Sil", sensitive=bool(selected)).connect(
            "activate", lambda _m: self.permanently_delete_selected()
        )
        menu.append(Gtk.SeparatorMenuItem())
        item("Çöp Kutusunu Boşalt").connect("activate", lambda _m: self.empty_trash())
        menu.show_all()
        menu.popup_at_pointer(event)

    def _show_errors(self, title, errors):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), flags=0,
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text("\n".join(errors[:10]))
        dialog.run()
        dialog.destroy()

    # -- operations ----------------------------------------------------
    def new_folder(self):
        path = fileops.create_folder(self.current_path)
        self.refresh()
        self.select_by_path(path)

        def undo_fn():
            fileops.trash_paths([path])
            self.refresh()

        def redo_fn():
            try:
                os.makedirs(path)
            except OSError:
                fileops.create_folder(self.current_path)
            self.refresh()

        self.window.push_undo(f'"{os.path.basename(path)}" klasörü oluşturuldu', undo_fn, redo_fn)

    def new_file(self):
        path = fileops.create_file(self.current_path)
        self.refresh()
        self.select_by_path(path)

        def undo_fn():
            fileops.trash_paths([path])
            self.refresh()

        def redo_fn():
            try:
                with open(path, "a", encoding="utf-8"):
                    pass
            except OSError:
                fileops.create_file(self.current_path)
            self.refresh()

        self.window.push_undo(f'"{os.path.basename(path)}" dosyası oluşturuldu', undo_fn, redo_fn)

    def copy_selected(self):
        paths = self.get_selected_paths()
        if paths:
            clipboard.copy(paths)

    def cut_selected(self):
        paths = self.get_selected_paths()
        if paths:
            clipboard.cut(paths)

    def paste(self):
        clipboard.request_paste(self._on_clipboard_data)

    def _on_clipboard_data(self, paths, is_cut):
        if not paths:
            return
        dest_dir = self.current_path
        if is_cut:
            def on_move_done(result):
                if result["errors"]:
                    self._show_errors("Taşınamadı", result["errors"])
                moved = result["moved"]
                if moved:
                    self._push_move_undo(moved)
                self.refresh()

            operations.run_move(self.window, paths, dest_dir, on_move_done)
        else:
            def on_copy_done(result):
                if result["errors"]:
                    self._show_errors("Kopyalanamadı", result["errors"])
                created = result["created"]
                if created:
                    def undo_fn():
                        operations.run_trash(self.window, created, lambda _r: self.refresh())

                    def redo_fn():
                        operations.run_copy(self.window, paths, dest_dir, lambda _r: self.refresh())

                    self.window.push_undo(f"{len(created)} öge kopyalandı", undo_fn, redo_fn)
                self.refresh()

            operations.run_copy(self.window, paths, dest_dir, on_copy_done)

    def _push_move_undo(self, moved):
        def undo_fn():
            pairs = [(new_p, old_p) for new_p, old_p in moved]
            operations.run_move_pairs(self.window, pairs, "Geri alınıyor...", lambda _r: self.refresh())

        def redo_fn():
            pairs = [(old_p, new_p) for new_p, old_p in moved]
            operations.run_move_pairs(self.window, pairs, "Yeniden yapılıyor...", lambda _r: self.refresh())

        self.window.push_undo(f"{len(moved)} öge taşındı", undo_fn, redo_fn)

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
        if response != Gtk.ResponseType.YES:
            return

        def on_trash_done(result):
            if result["errors"]:
                self._show_errors("Silinemedi", result["errors"])
            trashed = result["trashed"]
            if trashed:
                def undo_fn():
                    uris = [u for _p, u in trashed if u]
                    operations.run_restore(self.window, uris, lambda _r: self.refresh())

                def redo_fn():
                    paths2 = [p for p, _u in trashed]
                    operations.run_trash(self.window, paths2, lambda _r: self.refresh())

                self.window.push_undo(f"{len(trashed)} öge çöpe taşındı", undo_fn, redo_fn)
            self.refresh()

        operations.run_trash(self.window, paths, on_trash_done)

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
                    new_path = fileops.rename_path(old_path, new_name)
                except OSError as exc:
                    self.emit("status-changed", f"Yeniden adlandırılamadı: {exc}")
                    new_path = None
                if new_path:
                    def undo_fn(np=new_path, on=old_name):
                        try:
                            fileops.rename_path(np, on)
                        except OSError:
                            pass
                        self.refresh()

                    def redo_fn(op=old_path, nn=new_name):
                        try:
                            fileops.rename_path(op, nn)
                        except OSError:
                            pass
                        self.refresh()

                    self.window.push_undo(f'"{old_name}" yeniden adlandırıldı', undo_fn, redo_fn)
            self.refresh()
        dialog.destroy()

    def extract_selected(self):
        paths = self.get_selected_paths()
        archives = [p for p in paths if fileops.is_archive(p)]
        if not archives:
            return
        dest_dir = self.current_path

        def work():
            for archive_path in archives:
                fileops.extract_archive(archive_path, dest_dir)

        def on_done(result):
            if result["error"]:
                self._show_errors("Arşiv çıkartılamadı", [result["error"]])
            self.refresh()

        operations.run_background(self.window, "Çıkartılıyor...", work, on_done)

    def compress_selected(self):
        paths = self.get_selected_paths()
        if not paths:
            return
        base_name = os.path.basename(paths[0].rstrip("/")) if len(paths) == 1 else "Arşiv"
        dest_zip = fileops.unique_destination(self.current_path, f"{base_name}.zip")

        def work():
            fileops.create_zip(paths, dest_zip)

        def on_done(result):
            if result["error"]:
                self._show_errors("Sıkıştırılamadı", [result["error"]])
            self.refresh()

        operations.run_background(self.window, "Sıkıştırılıyor...", work, on_done)

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
        uris = [GLib.filename_to_uri(p) for p in self.get_selected_paths() if not self.is_trash]
        data.set_uris(uris)

    def _on_drag_data_received(self, _widget, _ctx, _x, _y, data, _info, _time):
        if self.is_trash:
            return
        uris = data.get_uris()
        paths = []
        for uri in uris:
            try:
                path, _frag = GLib.filename_from_uri(uri)
                paths.append(path)
            except GLib.Error:
                continue
        if paths:
            self._on_clipboard_data(paths, is_cut=False)
