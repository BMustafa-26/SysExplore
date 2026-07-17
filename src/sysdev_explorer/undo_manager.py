"""Bounded undo/redo stack for file operations performed in the UI."""

MAX_STACK = 30


class UndoManager:
    def __init__(self):
        self._undo_stack = []
        self._redo_stack = []

    def push(self, label, undo_fn, redo_fn):
        self._undo_stack.append({"label": label, "undo": undo_fn, "redo": redo_fn})
        if len(self._undo_stack) > MAX_STACK:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def can_undo(self):
        return bool(self._undo_stack)

    def can_redo(self):
        return bool(self._redo_stack)

    def undo(self):
        if not self._undo_stack:
            return None
        entry = self._undo_stack.pop()
        entry["undo"]()
        self._redo_stack.append(entry)
        return entry["label"]

    def redo(self):
        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        entry["redo"]()
        self._undo_stack.append(entry)
        return entry["label"]
