"""Main application window: tabs, breadcrumb toolbar, sidebar and panels."""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from sysdev_explorer.bottom_panel import QuickActionsPanel, RecentPanel, TerminalPanel
from sysdev_explorer.disk_utils import human_size
from sysdev_explorer.file_view import FileView
from sysdev_explorer.preferences import Preferences
from sysdev_explorer.side_panel import SidePanel
from sysdev_explorer.sidebar import Sidebar
from sysdev_explorer.undo_manager import UndoManager

HOME = os.path.expanduser("~")


class TabPage(Gtk.Box):
    """One breadcrumb+toolbar+file-view unit shown inside a notebook tab."""

    def __init__(self, window, start_path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.file_view = FileView(window, start_path)

        self.pack_start(self._build_toolbar(), False, False, 0)
        self.pack_start(self.file_view, True, True, 0)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.get_style_context().add_class("dim-label")
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_row.set_border_width(4)
        status_row.pack_start(self.status_label, False, False, 4)
        self.free_space_label = Gtk.Label(xalign=1)
        self.free_space_label.get_style_context().add_class("dim-label")
        status_row.pack_end(self.free_space_label, False, False, 4)
        self.pack_start(status_row, False, False, 0)

        self.file_view.connect("path-changed", self._on_path_changed)
        self.file_view.connect("status-changed", self._on_status_changed)
        self.file_view.connect("selection-changed", self._on_selection_changed)
        self.file_view.connect("open-terminal-request", lambda _v, path: window.open_terminal_at(path))
        self.file_view.connect("file-opened", lambda _v, path: window.recent_panel.register_opened(path))

        self._update_breadcrumb(start_path)

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.set_border_width(4)
        bar.get_style_context().add_class("nav-toolbar")

        self.back_btn = self._nav_button("go-previous-symbolic", self._on_back)
        self.forward_btn = self._nav_button("go-next-symbolic", self._on_forward)
        self.up_btn = self._nav_button("go-up-symbolic", self._on_up)
        self.home_btn = self._nav_button("go-home-symbolic", lambda _b: self.file_view.navigate(HOME))
        for b in (self.back_btn, self.forward_btn, self.up_btn, self.home_btn):
            bar.pack_start(b, False, False, 0)

        self.empty_trash_btn = Gtk.Button(label="Boşalt")
        self.empty_trash_btn.connect("clicked", lambda _b: self.file_view.empty_trash())
        self.empty_trash_btn.set_no_show_all(True)
        self.empty_trash_btn.hide()
        bar.pack_start(self.empty_trash_btn, False, False, 0)

        self.nav_stack = Gtk.Stack()
        bar.pack_start(self.nav_stack, True, True, 0)

        crumb_scroller = Gtk.ScrolledWindow()
        crumb_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.breadcrumb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        crumb_scroller.add(self.breadcrumb_box)
        self.nav_stack.add_named(crumb_scroller, "breadcrumb")

        self.address_entry = Gtk.Entry()
        self.address_entry.connect("activate", self._on_address_activate)
        self.address_entry.connect("key-press-event", self._on_address_key_press)
        self.nav_stack.add_named(self.address_entry, "address")
        self.nav_stack.set_visible_child_name("breadcrumb")

        self.search_entry = Gtk.SearchEntry(placeholder_text="Ara (Ctrl+F)")
        self.search_entry.set_width_chars(22)
        self.search_entry.connect("search-changed", self._on_search_changed)
        bar.pack_start(self.search_entry, False, False, 0)

        self.hidden_btn = Gtk.ToggleButton()
        self.hidden_btn.set_image(Gtk.Image.new_from_icon_name("view-conceal-symbolic", Gtk.IconSize.MENU))
        self.hidden_btn.set_tooltip_text("Gizli dosyaları göster (Ctrl+H)")
        self.hidden_btn.set_active(self.file_view.show_hidden)
        self.hidden_btn.connect("toggled", self._on_hidden_toggle)
        bar.pack_start(self.hidden_btn, False, False, 0)

        grid_btn = Gtk.ToggleButton()
        grid_btn.set_image(Gtk.Image.new_from_icon_name("view-grid-symbolic", Gtk.IconSize.MENU))
        grid_btn.set_active(self.file_view.stack.get_visible_child_name() == "grid")
        list_btn = Gtk.ToggleButton()
        list_btn.set_image(Gtk.Image.new_from_icon_name("view-list-symbolic", Gtk.IconSize.MENU))
        list_btn.set_active(self.file_view.stack.get_visible_child_name() == "list")
        grid_btn.connect("toggled", self._on_view_toggle, "grid", list_btn)
        list_btn.connect("toggled", self._on_view_toggle, "list", grid_btn)
        bar.pack_start(grid_btn, False, False, 0)
        bar.pack_start(list_btn, False, False, 0)

        return bar

    def _nav_button(self, icon_name, callback):
        btn = Gtk.Button.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        btn.connect("clicked", callback)
        return btn

    def _on_back(self, _b):
        self.file_view.go_back()

    def _on_forward(self, _b):
        self.file_view.go_forward()

    def _on_up(self, _b):
        self.file_view.go_up()

    def _on_view_toggle(self, toggle_btn, mode, other_btn):
        if toggle_btn.get_active():
            other_btn.set_active(False)
            self.file_view.set_view_mode(mode)
            self.window.preferences.set("view_mode", mode)
        elif not other_btn.get_active():
            toggle_btn.set_active(True)

    def _on_hidden_toggle(self, toggle_btn):
        if toggle_btn.get_active() != self.file_view.show_hidden:
            self.file_view.toggle_hidden_files()

    def sync_hidden_button(self):
        self.hidden_btn.set_active(self.file_view.show_hidden)

    def _on_search_changed(self, entry):
        self.file_view.set_search_text(entry.get_text())

    def enter_address_mode(self):
        if self.file_view.is_trash or self.file_view.current_path.startswith("network://"):
            return
        self.address_entry.set_text(self.file_view.current_path)
        self.nav_stack.set_visible_child_name("address")
        self.address_entry.grab_focus()
        self.address_entry.select_region(0, -1)

    def exit_address_mode(self):
        self.nav_stack.set_visible_child_name("breadcrumb")

    def _on_address_activate(self, entry):
        path = os.path.expanduser(entry.get_text().strip())
        if path:
            self.file_view.navigate(path)
        self.exit_address_mode()

    def _on_address_key_press(self, _entry, event):
        if event.keyval == Gdk.KEY_Escape:
            self.exit_address_mode()
            return True
        return False

    def _on_path_changed(self, _view, path):
        self._update_breadcrumb(path)
        self.empty_trash_btn.set_visible(self.file_view.is_trash)
        self.window.on_tab_path_changed(self, path)

    def _on_status_changed(self, _view, text):
        self.status_label.set_text(text)
        self.window.on_tab_status_changed(self, text)
        self._update_free_space()

    def _on_selection_changed(self, _view):
        self.window.on_tab_selection_changed(self)

    def _update_free_space(self):
        try:
            st = os.statvfs(self.file_view.current_path)
            free = st.f_frsize * st.f_bavail
            self.free_space_label.set_text(f"{human_size(free)} boş alan")
        except OSError:
            self.free_space_label.set_text("")

    def _update_breadcrumb(self, path):
        for child in list(self.breadcrumb_box.get_children()):
            self.breadcrumb_box.remove(child)

        self.back_btn.set_sensitive(self.file_view.can_go_back())
        self.forward_btn.set_sensitive(self.file_view.can_go_forward())

        if path == "trash:///":
            btn = Gtk.Button(label="🗑 Çöp Kutusu")
            btn.set_sensitive(False)
            self.breadcrumb_box.add(btn)
            self.breadcrumb_box.show_all()
            return
        if path.startswith("network://"):
            btn = Gtk.Button(label="🌐 Ağ Konumları")
            btn.set_sensitive(False)
            self.breadcrumb_box.add(btn)
            self.breadcrumb_box.show_all()
            return

        parts = path.rstrip("/").split("/")
        accumulated = ""
        for i, part in enumerate(parts):
            accumulated += part + "/"
            label = part if part else "/"
            btn = Gtk.Button(label=label)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("breadcrumb-btn")
            target = accumulated.rstrip("/") or "/"
            btn.connect("clicked", lambda _b, p=target: self.file_view.navigate(p))
            self.breadcrumb_box.add(btn)
            if i < len(parts) - 1:
                sep = Gtk.Label(label="›")
                sep.get_style_context().add_class("dim-label")
                self.breadcrumb_box.add(sep)
        self.breadcrumb_box.show_all()

    @property
    def title(self):
        if self.file_view.is_trash:
            return "Çöp Kutusu"
        return os.path.basename(self.file_view.current_path.rstrip("/")) or "/"


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="SysDev Explorer")
        self.set_default_size(1400, 900)
        self.preferences = Preferences()
        self.undo_manager = UndoManager()
        self._tabs = []

        self._build_headerbar()

        self.sidebar = Sidebar()
        self.sidebar.connect("location-selected", self._on_sidebar_location)

        self.side_panel = SidePanel()

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.connect("switch-page", self._on_switch_page)
        new_tab_btn = Gtk.Button.new_from_icon_name("tab-new-symbolic", Gtk.IconSize.MENU)
        new_tab_btn.set_relief(Gtk.ReliefStyle.NONE)
        new_tab_btn.connect("clicked", lambda _b: self.open_tab(HOME))
        self.notebook.set_action_widget(new_tab_btn, Gtk.PackType.END)
        new_tab_btn.show()

        top_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        top_paned.pack1(self.notebook, True, False)
        top_paned.pack2(self.side_panel, False, False)
        top_paned.set_position(1060)

        main_hbox = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_hbox.pack1(self.sidebar, False, False)
        main_hbox.pack2(top_paned, True, False)
        main_hbox.set_position(220)

        self.terminal_panel = TerminalPanel()
        self.terminal_panel.set_cwd_getter(lambda: self._active_tab().file_view.current_path if self._active_tab() else HOME)
        self.quick_actions = QuickActionsPanel(self._build_actions())
        self.recent_panel = RecentPanel()
        self.recent_panel.connect("file-activated", self._on_recent_activated)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom_box.set_border_width(4)
        bottom_box.pack_start(self.terminal_panel, True, True, 0)
        bottom_box.pack_start(self.quick_actions, False, False, 0)
        bottom_box.pack_start(self.recent_panel, True, True, 0)

        outer_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        outer_paned.pack1(main_hbox, True, False)
        outer_paned.pack2(bottom_box, False, False)
        outer_paned.set_position(620)

        self.add(outer_paned)
        self.show_all()

        self.open_tab(HOME, title="Ana Dizin")
        self.connect("key-press-event", self._on_key_press)

    # -- header ------------------------------------------------------------
    def _build_headerbar(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        icon = Gtk.Image.new_from_icon_name("system-file-manager", Gtk.IconSize.LARGE_TOOLBAR)
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title_box.pack_start(icon, False, False, 0)
        title_label = Gtk.Label(label="<b>SysDev Explorer</b>")
        title_label.set_use_markup(True)
        title_box.pack_start(title_label, False, False, 0)
        header.set_custom_title(title_box)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.MENU))
        popover = Gtk.Popover()
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu_box.set_border_width(6)

        def add_menu_item(label, callback):
            btn = Gtk.ModelButton(label=label)
            btn.get_child().set_xalign(0)
            btn.connect("clicked", callback)
            menu_box.pack_start(btn, False, False, 0)

        add_menu_item("Geri Al\tCtrl+Z", lambda _b: self.perform_undo())
        add_menu_item("Yinele\tCtrl+Shift+Z", lambda _b: self.perform_redo())
        menu_box.pack_start(Gtk.Separator(), False, False, 4)
        add_menu_item("Tercihler...", lambda _b: self.show_preferences())
        add_menu_item("Hakkında...", lambda _b: self.show_about())
        menu_box.show_all()
        popover.add(menu_box)
        menu_btn.set_popover(popover)
        header.pack_end(menu_btn)

        self.set_titlebar(header)

    def show_preferences(self):
        from sysdev_explorer.prefs_dialog import PreferencesDialog
        dialog = PreferencesDialog(self, self.preferences)
        dialog.run()
        dialog.destroy()

    def show_about(self):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("SysDev Explorer")
        dialog.set_version("1.0.0")
        dialog.set_comments("Git durumu, terminal ve hızlı işlemleri bir arada sunan Linux dosya yöneticisi")
        dialog.set_logo_icon_name("system-file-manager")
        dialog.run()
        dialog.destroy()

    # -- tabs ----------------------------------------------------------
    def open_tab(self, path, title=None):
        tab = TabPage(self, path)
        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label = Gtk.Label(label=title or tab.title)
        label_box.pack_start(label, False, False, 0)
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        label_box.pack_start(close_btn, False, False, 0)
        label_box.show_all()

        index = self.notebook.append_page(tab, label_box)
        tab.tab_label = label
        close_btn.connect("clicked", lambda _b: self.close_tab(tab))
        self.notebook.set_tab_reorderable(tab, True)
        tab.show_all()
        self._tabs.append(tab)
        self.notebook.set_current_page(index)
        return tab

    def close_tab(self, tab):
        if len(self._tabs) <= 1:
            return
        index = self.notebook.page_num(tab)
        if index != -1:
            self.notebook.remove_page(index)
        self._tabs.remove(tab)

    def _active_tab(self):
        page_num = self.notebook.get_current_page()
        if page_num == -1 or not self._tabs:
            return None
        widget = self.notebook.get_nth_page(page_num)
        return widget if isinstance(widget, TabPage) else None

    def _on_switch_page(self, _notebook, page, _index):
        if isinstance(page, TabPage):
            self.side_panel.update_selection(page.file_view.current_path)

    # -- signal plumbing from tabs -----------------------------------------
    def on_tab_path_changed(self, tab, path):
        if hasattr(tab, "tab_label"):
            tab.tab_label.set_text(tab.title)
        if tab is self._active_tab():
            self.side_panel.update_selection(path)
            self.sidebar.select_path(path)

    def on_tab_status_changed(self, tab, _text):
        pass

    def on_tab_selection_changed(self, tab):
        if tab is not self._active_tab():
            return
        selected = tab.file_view.get_selected_paths()
        if len(selected) > 1:
            self.side_panel.update_multi_selection(selected)
        elif selected:
            self.side_panel.update_selection(selected[-1])
        else:
            self.side_panel.update_selection(tab.file_view.current_path)

    def _on_recent_activated(self, _panel, path):
        directory = os.path.dirname(path)
        tab = self._active_tab() or self.open_tab(directory)
        tab.file_view.navigate(directory)
        GLib.idle_add(tab.file_view.select_by_path, path)

    def _on_sidebar_location(self, _sidebar, path):
        tab = self._active_tab()
        if tab:
            tab.file_view.navigate(path)
        else:
            self.open_tab(path)

    def open_terminal_at(self, path):
        self.terminal_panel.open_tab(path)

    def push_undo(self, label, undo_fn, redo_fn):
        self.undo_manager.push(label, undo_fn, redo_fn)

    def perform_undo(self):
        self.undo_manager.undo()

    def perform_redo(self):
        self.undo_manager.redo()

    # -- quick actions / shortcuts ------------------------------------------
    def _build_actions(self):
        def with_tab(fn):
            def wrapper():
                tab = self._active_tab()
                if tab:
                    fn(tab.file_view)
            return wrapper

        return {
            "new_folder": with_tab(lambda fv: fv.new_folder()),
            "new_file": with_tab(lambda fv: fv.new_file()),
            "rename": with_tab(lambda fv: fv.rename_selected()),
            "copy": with_tab(lambda fv: fv.copy_selected()),
            "cut": with_tab(lambda fv: fv.cut_selected()),
            "delete": with_tab(lambda fv: fv.delete_selected()),
            "terminal": with_tab(lambda fv: self.open_terminal_at(fv.current_path)),
            "properties": with_tab(lambda fv: self.side_panel.update_selection(
                (fv.get_selected_paths() or [fv.current_path])[0]
            )),
        }

    def _on_key_press(self, _widget, event):
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Entry, Gtk.TextView, Gtk.SearchEntry)):
            return False
        try:
            from gi.repository import Vte
            if isinstance(focus, Vte.Terminal):
                return False
        except (ImportError, ValueError):
            pass

        tab = self._active_tab()
        if not tab:
            return False
        fv = tab.file_view
        keyval = event.keyval
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)

        if keyval == Gdk.KEY_F2:
            fv.new_folder()
        elif ctrl and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            fv.new_file()
        elif keyval == Gdk.KEY_F6:
            fv.rename_selected()
        elif ctrl and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            fv.copy_selected()
        elif ctrl and keyval in (Gdk.KEY_x, Gdk.KEY_X):
            fv.cut_selected()
        elif ctrl and keyval in (Gdk.KEY_v, Gdk.KEY_V):
            fv.paste()
        elif keyval == Gdk.KEY_Delete:
            fv.delete_selected()
        elif ctrl and keyval in (Gdk.KEY_t, Gdk.KEY_T):
            self.open_terminal_at(fv.current_path)
        elif ctrl and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            tab.search_entry.grab_focus()
        elif ctrl and keyval in (Gdk.KEY_l, Gdk.KEY_L):
            tab.enter_address_mode()
        elif ctrl and keyval in (Gdk.KEY_h, Gdk.KEY_H):
            fv.toggle_hidden_files()
            tab.sync_hidden_button()
        elif ctrl and keyval in (Gdk.KEY_a, Gdk.KEY_A):
            fv.select_all()
        elif ctrl and shift and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            self.perform_redo()
        elif ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            self.perform_undo()
        elif alt and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = fv.get_selected_paths() or [fv.current_path]
            self.side_panel.update_selection(selected[0])
        else:
            return False
        return True
