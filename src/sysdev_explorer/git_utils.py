"""Lightweight git status helper, shells out to the system git binary."""
import shutil
import subprocess

_GIT = shutil.which("git")


def _run(args, cwd):
    if not _GIT:
        return None
    try:
        result = subprocess.run(
            [_GIT] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def repo_status(path):
    """Return dict with branch, last commit and file-change counts, or None."""
    if _run(["rev-parse", "--is-inside-work-tree"], path) is None:
        return None

    branch_out = _run(["branch", "--show-current"], path)
    branch = (branch_out or "").strip() or "(detached)"

    log_out = _run(["log", "-1", "--format=%h|%cr"], path)
    if log_out:
        parts = log_out.strip().split("|", 1)
        commit_hash = parts[0]
        commit_when = parts[1] if len(parts) > 1 else ""
    else:
        commit_hash, commit_when = "-", "henüz commit yok"

    status_out = _run(["status", "--porcelain=v1"], path) or ""
    modified = staged = untracked = deleted = 0
    for line in status_out.splitlines():
        if not line:
            continue
        index_state, work_state = line[0], line[1]
        if index_state == "?" and work_state == "?":
            untracked += 1
        else:
            if index_state not in (" ", "?"):
                staged += 1
            if work_state == "M":
                modified += 1
            elif work_state == "D":
                deleted += 1

    return {
        "branch": branch,
        "commit_hash": commit_hash,
        "commit_when": commit_when,
        "modified": modified,
        "staged": staged,
        "untracked": untracked,
        "deleted": deleted,
    }
