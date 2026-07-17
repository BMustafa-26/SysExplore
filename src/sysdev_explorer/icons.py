"""Icon lookup helpers backed by the active system icon theme (native look)."""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GdkPixbuf, Gtk  # noqa: E402

_theme = Gtk.IconTheme.get_default()
_cache = {}

FOLDER_FALLBACK = "folder"
FILE_FALLBACK = "text-x-generic"


def _load_named(name, size):
    key = (name, size)
    if key in _cache:
        return _cache[key]
    try:
        pixbuf = _theme.load_icon(name, size, Gtk.IconLookupFlags.FORCE_SIZE)
    except Exception:
        pixbuf = None
    _cache[key] = pixbuf
    return pixbuf


def pixbuf_for_path(path, size=48):
    is_dir = os.path.isdir(path)
    try:
        gfile = Gio.File.new_for_path(path)
        info = gfile.query_info(
            "standard::icon,standard::content-type",
            Gio.FileQueryInfoFlags.NONE,
            None,
        )
        gicon = info.get_icon()
        if gicon:
            lookup = _theme.lookup_by_gicon(gicon, size, Gtk.IconLookupFlags.FORCE_SIZE)
            if lookup:
                pixbuf = lookup.load_icon()
                if pixbuf:
                    return pixbuf
    except Exception:
        pass

    fallback = FOLDER_FALLBACK if is_dir else FILE_FALLBACK
    pixbuf = _load_named(fallback, size)
    if pixbuf:
        return pixbuf
    return GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size, size)


def named_pixbuf(name, size=16):
    return _load_named(name, size)


def thumbnail_for_image(path, max_size=256):
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max_size, max_size, True)
    except Exception:
        return None
