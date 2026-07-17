"""Cut/copy/paste backed by the real system clipboard (Gtk.Clipboard), so
state survives switching tabs/windows and is visible to clipboard managers.

Note: PyGObject's GTK3 bindings do not expose Gtk.Clipboard.set_with_data /
set_data (they are stubbed to always raise AttributeError), which is the
only GTK3 API for advertising multiple clipboard targets such as
"x-special/gnome-copied-files" or "text/uri-list" with per-target callbacks.
Because of that, this module can only use the text API (set_text /
request_text), which round-trips correctly within this app but is not
recognised by Nautilus/Dolphin's native "paste as file copy" — true
cross-file-manager clipboard interop is not achievable from GTK3 Python
bindings.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402


def _clipboard():
    return Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)


def _set(paths, is_cut):
    uris = [Gio.File.new_for_path(p).get_uri() for p in paths]
    action = "cut" if is_cut else "copy"
    payload = action + "\n" + "\n".join(uris)
    _clipboard().set_text(payload, -1)


def copy(paths):
    if paths:
        _set(paths, is_cut=False)


def cut(paths):
    if paths:
        _set(paths, is_cut=True)


def has_content():
    return _clipboard().wait_is_text_available()


def request_paste(callback):
    """Asynchronously read clipboard contents; callback(paths, is_cut)."""
    def on_text_received(_clip, text, _data):
        paths, is_cut = [], False
        if text:
            lines = [line for line in text.splitlines() if line]
            if lines and lines[0].strip() in ("copy", "cut"):
                is_cut = lines[0].strip() == "cut"
                paths = _uris_to_paths(lines[1:])
            else:
                paths = _uris_to_paths(lines)
        callback(paths, is_cut)

    _clipboard().request_text(on_text_received, None)


def _uris_to_paths(lines):
    paths = []
    for uri in lines:
        uri = uri.strip()
        if not uri.startswith("file://"):
            continue
        try:
            path, _frag = GLib.filename_from_uri(uri)
            paths.append(path)
        except GLib.Error:
            continue
    return paths
