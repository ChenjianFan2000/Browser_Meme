"""Sample owned Linux process trees and run-directory growth.

This is a polling soft guard, not a cgroup quota. CPU retains each observed
process identity's maximum self CPU; processes born and reaped between polls
are unobserved, so its cumulative value is explicitly a lower bound.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import time


def proc_snapshot():
    rows = {}
    ticks = os.sysconf('SC_CLK_TCK')
    page_bytes = os.sysconf('SC_PAGE_SIZE')
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            raw = path.read_text()
            fields = raw[raw.rfind(')') + 2:].split()
            pid = int(path.parent.name)
            rows[pid] = {'pid': pid, 'ppid': int(fields[1]), 'starttime': fields[19],
                'state': fields[0], 'cpu_seconds': (int(fields[11]) + int(fields[12])) / ticks,
                'rss_bytes': max(0, int(fields[21])) * page_bytes,
                'comm': raw[raw.find('(')+1:raw.rfind(')')]}
        except (OSError, ValueError, IndexError):
            pass
    return rows


def directory_bytes(root):
    """Logical and allocated regular-file bytes; no symlinks or double hardlinks."""
    logical = allocated = 0
    seen = set()
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not (Path(current)/name).is_symlink()]
        for name in files:
            try:
                info = (Path(current)/name).lstat()
                identity = (info.st_dev, info.st_ino)
                if stat.S_ISREG(info.st_mode) and identity not in seen:
                    seen.add(identity)
                    logical += info.st_size
                    allocated += info.st_blocks * 512
            except FileNotFoundError:
                pass
    return {'logical_bytes': logical, 'allocated_bytes': allocated}


class ResourceGuard:
    def __init__(self, roots, directory, *, limits):
        """Freeze numeric upper limits before spawn/first workload sample.

        Required keys: cpu_seconds, rss_bytes, disk_growth_bytes. Descendants are
        retained by PID+kernel starttime so observed detached children remain in
        subsequent samples and recycled PIDs are not charged to the task.
        """
        required = ('cpu_seconds', 'rss_bytes', 'disk_growth_bytes')
        if set(limits) != set(required) or any(isinstance(limits[key], bool) or
                not isinstance(limits[key], (int, float)) or not 0 < limits[key] < float('inf') for key in required):
            raise ValueError('freeze finite positive cpu_seconds/rss_bytes/disk_growth_bytes limits')
        self.limits = dict(limits)
        self.directory = Path(directory).resolve(strict=True)
        rows = proc_snapshot()
        self.identities = {int(pid): rows[int(pid)]['starttime'] for pid in roots}
        self.cpu = {}
        self.baseline_disk = directory_bytes(self.directory)
        self.peaks = {'cpu_seconds': 0, 'rss_bytes': 0, 'disk_growth_bytes': 0}

    def sample(self):
        rows = proc_snapshot()
        owned = {pid for pid, start in self.identities.items() if pid in rows and rows[pid]['starttime'] == start}
        while True:
            expanded = owned | {pid for pid, row in rows.items() if row['ppid'] in owned}
            if expanded == owned:
                break
            owned = expanded
        for pid in owned:
            row = rows[pid]
            identity = (pid, row['starttime'])
            self.identities[pid] = row['starttime']
            self.cpu[identity] = max(self.cpu.get(identity, 0), row['cpu_seconds'])
        disk = directory_bytes(self.directory)
        values = {'cpu_seconds': sum(self.cpu.values()),
                  'rss_bytes': sum(rows[pid]['rss_bytes'] for pid in owned),
                  'disk_growth_bytes': max(0, disk['logical_bytes']-self.baseline_disk['logical_bytes'])}
        self.peaks = {key: max(value, self.peaks[key]) for key, value in values.items()}
        exceeded = [key for key, value in values.items() if value >= self.limits[key]]
        return {'time_monotonic': time.monotonic(), **values, 'peaks': dict(self.peaks),
                'limits': dict(self.limits), 'exceeded': exceeded, 'stop_required': bool(exceeded),
                'processes': [rows[pid] for pid in sorted(owned)], 'disk': disk,
                'cpu_measurement': 'sampled_identity_self_cpu_cumulative_lower_bound',
                'enforcement': 'caller must stop and clean owned task; polling soft limit with overshoot',
                'disk_scope': 'run-directory regular files only; excludes tmpfs/browser cache outside directory'}
