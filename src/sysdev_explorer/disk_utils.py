"""Disk / mount point discovery without third-party dependencies."""
import os

_PSEUDO_FS = {
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
    "pstore", "bpf", "tracefs", "debugfs", "mqueue", "hugetlbfs",
    "securityfs", "autofs", "configfs", "fusectl", "binfmt_misc",
    "overlay", "squashfs", "efivarfs", "ramfs",
}


def human_size(num_bytes):
    if num_bytes is None:
        return "-"
    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < step or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= step
    return f"{size:.1f} PB"


def list_disks():
    """Return a list of dicts describing real, mounted filesystems."""
    disks = []
    seen_mounts = set()
    try:
        with open("/proc/mounts", "r") as fh:
            lines = fh.readlines()
    except OSError:
        lines = []

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount_point, fs_type = parts[0], parts[1], parts[2]
        mount_point = mount_point.encode().decode("unicode_escape")

        if fs_type in _PSEUDO_FS:
            continue
        if not device.startswith("/dev/") and "/" not in device[:1]:
            # allow network/bind mounts under /media, /mnt, /run/media
            if not mount_point.startswith(("/media", "/mnt", "/run/media", "/home")):
                continue
        if mount_point in seen_mounts:
            continue
        if mount_point.startswith(("/boot", "/snap", "/var/lib/docker")):
            continue

        try:
            st = os.statvfs(mount_point)
        except OSError:
            continue

        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        used = total - free
        if total == 0:
            continue

        seen_mounts.add(mount_point)
        label = os.path.basename(mount_point) or mount_point
        if mount_point == "/":
            label = "Sistem (/)"

        disks.append({
            "device": device,
            "mount_point": mount_point,
            "label": label,
            "fs_type": fs_type,
            "total": total,
            "used": used,
            "free": free,
            "used_fraction": (used / total) if total else 0.0,
        })

    disks.sort(key=lambda d: d["mount_point"] != "/")
    return disks
