"""Background copy/move/trash/restore jobs with a progress dialog and
conflict resolution, so the UI thread never blocks on filesystem work.
"""
import os
import shutil
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from sysdev_explorer import fileops


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()


class _ProgressDialog(Gtk.Dialog):
    def __init__(self, parent, title, allow_cancel=True):
        super().__init__(title=title, transient_for=parent)
        self.set_default_size(420, 110)
        self.set_deletable(False)
        box = self.get_content_area()
        box.set_border_width(16)
        box.set_spacing(8)
        self.label = Gtk.Label(label="Hazırlanıyor...", xalign=0)
        self.label.set_line_wrap(True)
        box.add(self.label)
        self.bar = Gtk.ProgressBar()
        box.add(self.bar)
        self.cancel_token = CancelToken()
        if allow_cancel:
            self.add_button("İptal", Gtk.ResponseType.CANCEL)
            self.connect("response", lambda _d, _r: self.cancel_token.cancel())

    def update(self, text, fraction):
        if text is not None:
            self.label.set_text(text)
        if fraction is None:
            self.bar.pulse()
        else:
            self.bar.set_fraction(max(0.0, min(1.0, fraction)))
        return False


class _Job:
    """Runs background work, showing a progress dialog only if the job takes
    longer than SHOW_DELAY_MS so quick operations don't flash a dialog.
    """

    SHOW_DELAY_MS = 350

    def __init__(self, parent, title, allow_cancel=True):
        self.dialog = _ProgressDialog(parent, title, allow_cancel)
        self._finished = False
        self._shown = False
        GLib.timeout_add(self.SHOW_DELAY_MS, self._maybe_show)

    def _maybe_show(self):
        if not self._finished and not self._shown:
            self.dialog.show_all()
            self._shown = True
        return False

    @property
    def cancelled(self):
        return self.dialog.cancel_token.cancelled

    def report(self, text, fraction):
        GLib.idle_add(self.dialog.update, text, fraction)

    def ask_conflict(self, name):
        """Blocks the calling (worker) thread until the user answers."""
        result = {}
        done = threading.Event()

        def ask():
            if not self._shown:
                self._maybe_show()
            dlg = Gtk.MessageDialog(
                transient_for=self.dialog,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                text=f'"{name}" zaten var',
            )
            dlg.format_secondary_text("Ne yapmak istersiniz?")
            dlg.add_buttons("Atla", 1, "Yeniden Adlandır", 2, "Değiştir", 3)
            check = Gtk.CheckButton(label="Kalan tüm çakışmalar için uygula")
            dlg.get_content_area().pack_start(check, False, False, 4)
            dlg.show_all()
            response = dlg.run()
            result["choice"] = {1: "skip", 2: "rename", 3: "overwrite"}.get(response, "skip")
            result["apply_all"] = check.get_active()
            dlg.destroy()
            done.set()
            return False

        GLib.idle_add(ask)
        done.wait()
        return result["choice"], result["apply_all"]

    def finish(self, on_done, payload):
        self._finished = True

        def _finish():
            if self._shown:
                self.dialog.destroy()
            on_done(payload)
            return False

        GLib.idle_add(_finish)


def _count_files(path):
    if os.path.isdir(path) and not os.path.islink(path):
        total = 0
        for _root, _dirs, files in os.walk(path):
            total += len(files)
        return total
    return 1


def _resolve_destination(job, src_name, dest_dir, apply_all_state):
    """Returns final dest path, or None if the item should be skipped."""
    candidate = os.path.join(dest_dir, src_name)
    if not os.path.exists(candidate):
        return candidate
    choice = apply_all_state.get("choice")
    if choice is None:
        choice, apply_all = job.ask_conflict(src_name)
        if apply_all:
            apply_all_state["choice"] = choice
    if choice == "skip":
        return None
    if choice == "overwrite":
        return candidate
    return fileops.unique_destination(dest_dir, src_name)


def _copy_one(src, dest, job, counter, total):
    if os.path.isdir(src) and not os.path.islink(src):
        os.makedirs(dest, exist_ok=True)
        for entry in sorted(os.scandir(src), key=lambda e: e.name):
            if job.cancelled:
                return
            target = os.path.join(dest, entry.name)
            if entry.is_dir(follow_symlinks=False):
                _copy_one(entry.path, target, job, counter, total)
            else:
                shutil.copy2(entry.path, target)
                counter[0] += 1
                job.report(entry.name, counter[0] / total if total else None)
    else:
        shutil.copy2(src, dest)
        counter[0] += 1
        job.report(os.path.basename(src), counter[0] / total if total else None)


def run_copy(window, paths, dest_dir, on_done):
    job = _Job(window, "Kopyalanıyor...")
    apply_all_state = {}

    def work():
        total = sum(_count_files(p) for p in paths) or 1
        counter = [0]
        created, errors = [], []
        for src in paths:
            if job.cancelled:
                break
            name = os.path.basename(src.rstrip("/"))
            dest = _resolve_destination(job, name, dest_dir, apply_all_state)
            if dest is None:
                continue
            try:
                _copy_one(src, dest, job, counter, total)
                created.append(dest)
            except OSError as exc:
                errors.append(f"{name}: {exc}")
        job.finish(on_done, {"errors": errors, "cancelled": job.cancelled, "created": created})

    threading.Thread(target=work, daemon=True).start()


def run_move(window, paths, dest_dir, on_done):
    job = _Job(window, "Taşınıyor...")
    apply_all_state = {}

    def work():
        moved, errors = [], []
        total = len(paths) or 1
        for i, src in enumerate(paths, start=1):
            if job.cancelled:
                break
            name = os.path.basename(src.rstrip("/"))
            job.report(name, i / total)
            dest = _resolve_destination(job, name, dest_dir, apply_all_state)
            if dest is None:
                continue
            try:
                if os.path.exists(dest) and dest != src:
                    if os.path.isdir(dest) and not os.path.islink(dest):
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)
                shutil.move(src, dest)
                moved.append((dest, src))
            except (OSError, shutil.Error) as exc:
                errors.append(f"{name}: {exc}")
        job.finish(on_done, {"errors": errors, "cancelled": job.cancelled, "moved": moved})

    threading.Thread(target=work, daemon=True).start()


def run_move_pairs(window, pairs, title, on_done):
    """Move each (src, dest) pair to its exact target path, no conflict UI.
    Used for undo/redo of a move, where sources may come from many dirs.
    """
    job = _Job(window, title, allow_cancel=False)

    def work():
        moved, errors = [], []
        total = len(pairs) or 1
        for i, (src, dest) in enumerate(pairs, start=1):
            job.report(os.path.basename(src.rstrip("/")), i / total)
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(src, dest)
                moved.append((dest, src))
            except (OSError, shutil.Error) as exc:
                errors.append(f"{os.path.basename(src)}: {exc}")
        job.finish(on_done, {"errors": errors, "moved": moved})

    threading.Thread(target=work, daemon=True).start()


def run_trash(window, paths, on_done):
    job = _Job(window, "Çöp kutusuna taşınıyor...", allow_cancel=False)

    def work():
        trashed, errors = [], []
        total = len(paths) or 1
        for i, path in enumerate(paths, start=1):
            job.report(os.path.basename(path.rstrip("/")), i / total)
            trash_uri, error = fileops.trash_path_tracked(path)
            if error:
                errors.append(f"{os.path.basename(path)}: {error}")
            else:
                trashed.append((path, trash_uri))
        job.finish(on_done, {"errors": errors, "cancelled": False, "trashed": trashed})

    threading.Thread(target=work, daemon=True).start()


def run_restore(window, trash_uris, on_done):
    job = _Job(window, "Geri yükleniyor...", allow_cancel=False)

    def work():
        restored, errors = [], []
        for uri in trash_uris:
            ok, orig_path, error = fileops.restore_from_trash(uri)
            if ok:
                restored.append((orig_path, uri))
            else:
                errors.append(error or uri)
        job.finish(on_done, {"errors": errors, "restored": restored})

    threading.Thread(target=work, daemon=True).start()


def run_background(window, title, work_fn, on_done):
    """Generic pulsing-progress job, e.g. for archive extract/compress."""
    job = _Job(window, title, allow_cancel=False)
    stop_pulse = threading.Event()

    def pulse():
        if stop_pulse.is_set():
            return False
        job.report(None, None)
        return True

    GLib.timeout_add(120, pulse)

    def work():
        try:
            result = work_fn()
            error = None
        except Exception as exc:  # noqa: BLE001
            result = None
            error = str(exc)
        stop_pulse.set()
        job.finish(on_done, {"result": result, "error": error})

    threading.Thread(target=work, daemon=True).start()
