"""Volatility signal from git history.

Counts, per file, how many commits touched it in a recent window (default 6
months) — a single `git log` pass, no per-file calls. This is the only piece
that requires git; without it every module reads as low-volatility.
"""
from __future__ import annotations

import os
import subprocess


def git_root(path: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def commit_counts(path: str, since: str = "6 months ago") -> dict[str, int]:
    """Return {absolute_file_path: commit_count} over the recent window.

    Empty dict if `path` is not in a git repo (volatility then defaults to 0).
    """
    root = git_root(path)
    if root is None:
        return {}
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", f"--since={since}",
             "--name-only", "--pretty=format:", "--", "*.py"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    counts: dict[str, int] = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        abspath = os.path.normpath(os.path.join(root, line))
        counts[abspath] = counts.get(abspath, 0) + 1
    return counts
