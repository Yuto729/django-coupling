"""Volatility signal from git history.

Counts, per file, how many commits touched it in a recent window (default 6
months). This is the only piece that requires git; without it every module
reads as low-volatility.

Hardening (the git sensor degrades in the AI-coding era, where one commit may
touch many unrelated files):
  1. --no-merges            : merge commits are not real edits
  2. exclude bulk commits   : commits touching > max_files are dropped, because
                              a single N-file commit pollutes N files at once
  3. self-reported confidence: the commit-size distribution is measured and the
                              tool reports how trustworthy the signal is, rather
                              than pretending it is always reliable.
"""
from __future__ import annotations

import os
import subprocess

_MARK = "__djc_commit__"


def git_root(path: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _confidence(sizes: list[int], max_files: int) -> str:
    """Rate how trustworthy the volatility signal is, from commit-size spread."""
    if not sizes:
        return "n/a"
    s = sorted(sizes)
    m = len(s)
    median = s[m // 2]
    bulk_pct = 100 * sum(1 for x in s if x > max_files) / m
    if median <= 3 and bulk_pct < 10:
        return "high"
    if median <= 7 and bulk_pct < 25:
        return "medium"
    return "low"


def commit_counts(path: str, since: str = "6 months ago", max_files: int = 30):
    """Return (counts, diagnostics).

    counts: {absolute_file_path: commit_count} over the window, excluding merges
            and commits touching more than `max_files` files.
    diagnostics: dict describing the commit-size distribution and a `confidence`
            label, or None if `path` is not a git repo.
    """
    root = git_root(path)
    if root is None:
        return {}, None
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", f"--since={since}", "--no-merges",
             f"--pretty=format:{_MARK}%H", "--name-only", "--", "*.py"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}, None

    # group output into per-commit file lists
    commits: list[list[str]] = []
    cur: list[str] | None = None
    for line in out.stdout.splitlines():
        if line.startswith(_MARK):
            cur = []
            commits.append(cur)
            continue
        line = line.strip()
        if line and cur is not None:
            cur.append(line)

    counts: dict[str, int] = {}
    sizes: list[int] = []        # files-per-commit, for commits touching >=1 .py
    excluded = 0
    for files in commits:
        n = len(files)
        if n == 0:
            continue  # commit touched no .py files
        sizes.append(n)
        if n > max_files:
            excluded += 1
            continue  # bulk/mechanical commit — drop to avoid co-touch pollution
        for f in files:
            ap = os.path.normpath(os.path.join(root, f))
            counts[ap] = counts.get(ap, 0) + 1

    s = sorted(sizes)
    diagnostics = {
        "commits": len(sizes),
        "counted_commits": len(sizes) - excluded,
        "excluded_bulk": excluded,
        "max_commit_files": max_files,
        "median_files": s[len(s) // 2] if s else 0,
        "mean_files": round(sum(s) / len(s), 1) if s else 0.0,
        "p90_files": s[min(len(s) - 1, int(len(s) * 0.9))] if s else 0,
        "confidence": _confidence(sizes, max_files),
    }
    return counts, diagnostics
