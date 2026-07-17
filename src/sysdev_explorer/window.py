"""Main application window: tabs, breadcrumb toolbar, sidebar and panels."""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from sysdev_explorer.bottom_panel import QuickActionsPanel, RecentPanel, TerminalPanel
from sysdev_explorer.disk_utils import human_size
from sysdev_explorer.fileops import ClipboardState, open_terminal_here
from sysdev_explorer.file_view import FileView
from sysdev_explorer.side_panel import SidePanel
from sysdev_explorer.sidebar import Sidebar

HOME = os.path.expanduser("~")


class TabPage(Gtk.Box):
    """One breadcrumb+toolbar+file-view unit shown inside a notebook tab."""

    def __init__(self, window, start_path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.file_view = FileView(window.clipboard_state, start_path)

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

        crumb_scroller = Gtk.ScrolledWindow()
        crumb_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.breadcrumb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        crumb_scroller.add(self.breadcrumb_box)
        bar.pack_start(crumb_scroller, True, True, 0)

        self.search_entry = Gtk.SearchEntry(placeholder_text="Ara (Ctrl+F)")
        self.search_entry.set_width_chars(22)
        self.search_entry.connect("search-changed", self._on_search_changed)
        bar.pack_start(self.search_entry, False, False, 0)

        grid_btn = Gtk.ToggleButton()
        grid_btn.set_image(Gtk.Image.new_from_icon_name("view-grid-symbolic", Gtk.IconSize.MENU))
        grid_btn.set_active(True)
        list_btn = Gtk.ToggleButton()
        list_btn.set_image(Gtk.Image.new_from_icon_name("view-list-symbolic", Gtk.IconSize.MENU))
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
        elif not other_btn.get_active():
            toggle_btn.set_active(True)

    def _on_search_changed(self, entry):
        self.file_view.set_search_text(entry.get_text())

    def _on_path_changed(self, _view, path):
        self._update_breadcrumb(path)
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

        if path.startswith(("trash://", "network://")):
            btn = Gtk.Button(label=path)
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
        return os.path.basename(self.file_view.current_path.rstrip("/")) or "/"


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="SysDev Explorer")
        self.set_default_size(1400, 900)
        self.clipboard_state = ClipboardState()
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
        self.set_titlebar(header)

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
        if selected:
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
        elif alt and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = fv.get_selected_paths() or [fv.current_path]
            self.side_panel.update_selection(selected[0])
        else:
            return False
        return True
