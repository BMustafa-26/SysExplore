"""Filesystem operations used by the file view: copy, move, delete, rename..."""
import configparser
import mimetypes
import os
import shutil
import stat as statmod
import tarfile
import time
import zipfile
from urllib.parse import unquote

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from sysdev_explorer.disk_utils import human_size, list_disks  # noqa: E402


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


# -- Trash: implemented directly against the freedesktop.org Trash spec
# (~/.local/share/Trash/{files,info} + per-mount .Trash-$uid dirs) rather
# than through the trash:// GVFS URI scheme. Listing/browsing trash:// only
# works when gvfsd is running under a D-Bus session, which many minimal or
# tiling-WM Linux setups don't have running; actually moving a file *to*
# trash via Gio.File.trash() works everywhere since GIO implements that
# part of the spec locally, with no daemon involved.
def _trash_home_dir():
    xdg_data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(xdg_data_home, "Trash")


def _trash_dirs():
    dirs = [_trash_home_dir()]
    uid = os.getuid()
    try:
        for disk in list_disks():
            mount_point = disk["mount_point"]
            if mount_point == "/":
                continue
            for candidate in (
                os.path.join(mount_point, ".Trash", str(uid)),
                os.path.join(mount_point, f".Trash-{uid}"),
            ):
                if os.path.isdir(candidate):
                    dirs.append(candidate)
    except OSError:
        pass
    return dirs


def _trashinfo_path(trash_path):
    trash_root = os.path.dirname(os.path.dirname(trash_path))
    return os.path.join(trash_root, "info", os.path.basename(trash_path) + ".trashinfo")


def _parse_trashinfo(info_path):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(info_path, encoding="utf-8")
        orig_path = unquote(parser.get("Trash Info", "Path"))
        deletion_date = parser.get("Trash Info", "DeletionDate", fallback="")
    except (OSError, configparser.Error, KeyError):
        return None, None
    return orig_path, deletion_date


def list_trash_items():
    """Return a list of dicts describing everything currently in the trash."""
    items = []
    for trash_dir in _trash_dirs():
        files_dir = os.path.join(trash_dir, "files")
        if not os.path.isdir(files_dir):
            continue
        for name in os.listdir(files_dir):
            trash_path = os.path.join(files_dir, name)
            orig_path, _deletion_date = _parse_trashinfo(_trashinfo_path(trash_path))
            try:
                st = os.lstat(trash_path)
                size = 0 if statmod.S_ISDIR(st.st_mode) else st.st_size
            except OSError:
                size = 0
            items.append({
                "uri": trash_path,
                "name": name,
                "orig_path": orig_path or "",
                "size": size,
            })
    return items


def trash_path_tracked(path):
    """Trash a single path, returning (trash_file_path_or_None, error_or_None)."""
    try:
        Gio.File.new_for_path(path).trash(None)
    except GLib.Error as exc:
        return None, exc.message
    best, best_mtime = None, -1.0
    for item in list_trash_items():
        if item["orig_path"] == path:
            try:
                mtime = os.lstat(item["uri"]).st_mtime
            except OSError:
                mtime = 0.0
            if mtime >= best_mtime:
                best_mtime, best = mtime, item["uri"]
    return best, None


def restore_from_trash(trash_path):
    """Move a trashed item back to its original location. Returns
    (success, orig_path_or_None, error_or_None)."""
    orig_path, _deletion_date = _parse_trashinfo(_trashinfo_path(trash_path))
    if not orig_path:
        return False, None, "Özgün konum bilgisi bulunamadı"
    try:
        os.makedirs(os.path.dirname(orig_path), exist_ok=True)
        dest = orig_path if not os.path.exists(orig_path) else unique_destination(
            os.path.dirname(orig_path), os.path.basename(orig_path)
        )
        shutil.move(trash_path, dest)
    except (OSError, shutil.Error) as exc:
        return False, orig_path, str(exc)
    try:
        os.remove(_trashinfo_path(trash_path))
    except OSError:
        pass
    return True, orig_path, None


def permanently_delete_trash_items(trash_paths):
    errors = []
    for trash_path in trash_paths:
        try:
            if os.path.isdir(trash_path) and not os.path.islink(trash_path):
                shutil.rmtree(trash_path)
            else:
                os.remove(trash_path)
        except OSError as exc:
            errors.append(f"{os.path.basename(trash_path)}: {exc}")
            continue
        try:
            os.remove(_trashinfo_path(trash_path))
        except OSError:
            pass
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


_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


def is_archive(path):
    return path.lower().endswith(_ARCHIVE_SUFFIXES)


def extract_archive(archive_path, dest_dir):
    """Extract archive_path into dest_dir, guarding against zip-slip / tar
    path-traversal by rejecting any member that would land outside dest_dir.
    """
    dest_abs = os.path.abspath(dest_dir)
    lower = archive_path.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            safe_names = []
            for name in zf.namelist():
                target = os.path.abspath(os.path.join(dest_dir, name))
                if target == dest_abs or target.startswith(dest_abs + os.sep):
                    safe_names.append(name)
            zf.extractall(dest_dir, members=safe_names)
    else:
        with tarfile.open(archive_path) as tf:
            safe_members = []
            for member in tf.getmembers():
                target = os.path.abspath(os.path.join(dest_dir, member.name))
                if target == dest_abs or target.startswith(dest_abs + os.sep):
                    safe_members.append(member)
            tf.extractall(dest_dir, members=safe_members)


def create_zip(paths, dest_zip):
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            path = path.rstrip("/")
            if os.path.isdir(path) and not os.path.islink(path):
                base = os.path.dirname(path)
                for root, _dirs, files in os.walk(path):
                    for f in files:
                        full = os.path.join(root, f)
                        zf.write(full, os.path.relpath(full, base))
            else:
                zf.write(path, os.path.basename(path))


def is_executable_file(path):
    return os.path.isfile(path) and not os.path.islink(path) and os.access(path, os.X_OK)


def run_executable(path):
    try:
        GLib.spawn_async(
            [path],
            working_directory=os.path.dirname(path),
            flags=GLib.SpawnFlags.SEARCH_PATH,
        )
        return True
    except GLib.Error:
        return False
