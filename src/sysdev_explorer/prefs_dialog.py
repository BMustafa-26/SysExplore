"""Preferences dialog: default hidden-files/view-mode/theme behaviour."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class PreferencesDialog(Gtk.Dialog):
    def __init__(self, parent, preferences):
        super().__init__(title="Tercihler", transient_for=parent, modal=True)
        self.preferences = preferences
        self.add_buttons("Kapat", Gtk.ResponseType.CLOSE)
        self.set_default_size(360, 200)

        grid = Gtk.Grid(row_spacing=12, column_spacing=16)
        grid.set_border_width(16)
        self.get_content_area().add(grid)

        grid.attach(Gtk.Label(label="Gizli dosyaları göster", xalign=0), 0, 0, 1, 1)
        self.hidden_switch = Gtk.Switch()
        self.hidden_switch.set_active(preferences.get("show_hidden"))
        self.hidden_switch.set_halign(Gtk.Align.END)
        self.hidden_switch.connect("notify::active", self._on_hidden_changed)
        grid.attach(self.hidden_switch, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Varsayılan görünüm", xalign=0), 0, 1, 1, 1)
        self.view_combo = Gtk.ComboBoxText()
        self.view_combo.append("grid", "Izgara")
        self.view_combo.append("list", "Liste")
        self.view_combo.set_active_id(preferences.get("view_mode"))
        self.view_combo.connect("changed", self._on_view_changed)
        grid.attach(self.view_combo, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Tema", xalign=0), 0, 2, 1, 1)
        self.theme_combo = Gtk.ComboBoxText()
        self.theme_combo.append("dark", "Koyu (uygulamaya özel)")
        self.theme_combo.append("system", "Sistem teması")
        self.theme_combo.set_active_id(preferences.get("theme"))
        self.theme_combo.connect("changed", self._on_theme_changed)
        grid.attach(self.theme_combo, 1, 2, 1, 1)

        note = Gtk.Label(
            xalign=0, wrap=True,
            label="Tema değişikliği yeni açılan pencerelerde etkili olur.",
        )
        note.get_style_context().add_class("dim-label")
        grid.attach(note, 0, 3, 2, 1)

        self.show_all()

    def _on_hidden_changed(self, switch, _pspec):
        self.preferences.set("show_hidden", switch.get_active())

    def _on_view_changed(self, combo):
        active = combo.get_active_id()
        if active:
            self.preferences.set("view_mode", active)

    def _on_theme_changed(self, combo):
        active = combo.get_active_id()
        if active:
            self.preferences.set("theme", active)
