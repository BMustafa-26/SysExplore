"""Filesystem operations used by the file view: copy, move, delete, rename..."""
import mimetypes
import os
import shutil
import stat as statmod
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from sysdev_explorer.disk_utils import human_size  # noqa: E402


class ClipboardState:
    """Tracks a pending copy/cut selection for paste."""

    def __init__(self):
        self.paths = []
        self.is_cut = False

    def set(self, paths, is_cut):
        self.paths = list(paths)
        self.is_cut = is_cut

    def clear(self):
        self.paths = []
        self.is_cut = False

    @property
    def has_content(self):
        return bool(self.paths)


def unique_destination(dest_dir, name):
    """Avoid clobbering an existing file by appending (1), (2)..."""
    candidate = os.path.join(dest_dir, name)
    if not os.path.exists(candidate):
        return candidate
    base, ext = os.path.splitext(name)
    n = 1
    while True:
        candidate = os.path.join(dest_dir, f"{base} ({n}){ext}")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def copy_paths(paths, dest_dir):
    errors = []
    for src in paths:
        try:
            dest = unique_destination(dest_dir, os.path.basename(src.rstrip("/")))
            if os.path.isdir(src) and not os.path.islink(src):
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
        except (OSError, shutil.Error) as exc:
            errors.append(f"{src}: {exc}")
    return errors


def move_paths(paths, dest_dir):
    errors = []
    for src in paths:
        try:
            dest = unique_destination(dest_dir, os.path.basename(src.rstrip("/")))
            shutil.move(src, dest)
        except (OSError, shutil.Error) as exc:
            errors.append(f"{src}: {exc}")
    return errors


def trash_paths(paths):
    errors = []
    for path in paths:
        try:
            Gio.File.new_for_path(path).trash(None)
        except GLib.Error as exc:
            errors.append(f"{path}: {exc.message}")
    return errors


def rename_path(path, new_name):
    new_path = os.path.join(os.path.dirname(path.rstrip("/")), new_name)
    os.rename(path, new_path)
    return new_path


def create_folder(parent_dir, name="Yeni Klasör"):
    path = unique_destination(parent_dir, name)
    os.makedirs(path)
    return path


def create_file(parent_dir, name="Yeni Dosya.txt"):
    path = unique_destination(parent_dir, name)
    with open(path, "a", encoding="utf-8"):
        pass
    return path


def format_mtime(ts):
    try:
        return time.strftime("%d %b %Y %H:%M", time.localtime(ts))
    except (OSError, ValueError, OverflowError):
        return "-"


def dir_summary_async(path, callback):
    """Recursively count folders/files/size under path in a worker thread."""
    def worker():
        n_dirs = n_files = 0
        total = 0
        try:
            for root, dirs, files in os.walk(path, onerror=lambda e: None):
                n_dirs += len(dirs)
                n_files += len(files)
                for f in files:
                    try:
                        total += os.lstat(os.path.join(root, f)).st_size
                    except OSError:
                        pass
        except OSError:
            pass
        GLib.idle_add(callback, n_dirs, n_files, total)

    GLib.Thread.new("dir-summary", worker)


def permissions_string(mode):
    return statmod.filemode(mode)


def permission_bits(mode):
    return {
        "owner_r": bool(mode & statmod.S_IRUSR),
        "owner_w": bool(mode & statmod.S_IWUSR),
        "owner_x": bool(mode & statmod.S_IXUSR),
        "group_r": bool(mode & statmod.S_IRGRP),
        "group_w": bool(mode & statmod.S_IWGRP),
        "group_x": bool(mode & statmod.S_IXGRP),
        "other_r": bool(mode & statmod.S_IROTH),
        "other_w": bool(mode & statmod.S_IWOTH),
        "other_x": bool(mode & statmod.S_IXOTH),
    }


_BIT_FLAGS = {
    "owner_r": statmod.S_IRUSR, "owner_w": statmod.S_IWUSR, "owner_x": statmod.S_IXUSR,
    "group_r": statmod.S_IRGRP, "group_w": statmod.S_IWGRP, "group_x": statmod.S_IXGRP,
    "other_r": statmod.S_IROTH, "other_w": statmod.S_IWOTH, "other_x": statmod.S_IXOTH,
}


def set_permission_bit(path, key, enabled):
    mode = os.stat(path).st_mode
    flag = _BIT_FLAGS[key]
    mode = (mode | flag) if enabled else (mode & ~flag)
    os.chmod(path, statmod.S_IMODE(mode))


def guess_type_label(path):
    if os.path.isdir(path):
        return "Klasör"
    mime, _ = mimetypes.guess_type(path)
    return mime or "Bilinmeyen dosya türü"


def open_with_default_app(path):
    Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)


def open_terminal_here(path):
    """Best-effort: launch the user's terminal emulator in `path`."""
    candidates = [
        ("x-terminal-emulator", []),
        ("gnome-terminal", ["--working-directory", path]),
        ("konsole", ["--workdir", path]),
        ("xfce4-terminal", ["--working-directory", path]),
        ("tilix", ["-w", path]),
        ("alacritty", ["--working-directory", path]),
        ("xterm", []),
    ]
    for binary, extra_args in candidates:
        exe = shutil.which(binary)
        if not exe:
            continue
        argv = [exe] + extra_args
        try:
            GLib.spawn_async(
                argv,
                working_directory=path if not extra_args else None,
                flags=GLib.SpawnFlags.SEARCH_PATH,
            )
            return True
        except GLib.Error:
            continue
    return False
