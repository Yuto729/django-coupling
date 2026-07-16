"""Diff mode: how much did the currently-changed files worsen coupling?

Instead of the absolute state, this reports the *delta* attributable to the
changed files: new issues, balance regressions, and new/worsened God candidates.

Mechanism (incremental — no whole-project baseline run):
  - changed files come from `git diff --name-only [<ref>]` (+ untracked)
  - for each changed file, its "before" version is fetched with `git show`
    and its "after" version is read from the working tree
  - only the changed files are parsed (both versions); cost scales with the
    size of the change, not the repo

Scope: only edges *originating from* changed files (plus their God classes).
Second-order effects on unchanged importers (volatility drift, or a file being
moved across a layer) are out of scope — see README/SKILL.
"""
from __future__ import annotations

import ast
import os
import subprocess

from .classify import distance_score, volatility_score
from .config import load_config
from .godclass import god_in_tree
from .parser import (
    _is_test_file, discover_project_root, edges_from_tree, iter_py_files,
    module_name,
)
from .score import balance_score, detect_issue
from .volatility import commit_counts, git_root

_SEV_RANK = {None: 0, "high": 1, "critical": 2}
_BUILTIN_SKIP = {"__pycache__", "migrations", "node_modules", "venv", ".venv"}


def _git(root, args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)


def _changed_paths(root, ref):
    """git-root-relative .py paths changed vs `ref` (working tree vs HEAD if None)."""
    base = ref or "HEAD"
    out = _git(root, ["diff", "--name-only", base, "--", "*.py"])
    paths = [l for l in out.stdout.splitlines() if l.strip()]
    if ref is None:  # also include new, not-yet-committed files
        unt = _git(root, ["ls-files", "--others", "--exclude-standard", "--", "*.py"])
        paths += [l for l in unt.stdout.splitlines() if l.strip()]
    return sorted(set(paths))


def _content_at(root, ref, gitrel):
    out = _git(root, ["show", f"{ref}:{gitrel}"])
    return out.stdout if out.returncode == 0 else None


def _parse(src):
    if src is None:
        return None
    try:
        return ast.parse(src)
    except (SyntaxError, ValueError):
        return None


def _edge_map(mod, tree, internal, is_package, layer_rank, counts, abspaths):
    """{(src,tgt): scored edge dict} for one module's outgoing edges."""
    result = {}
    for e in edges_from_tree(mod, tree, internal, is_package):
        tgt = e["tgt"]
        dist, dist_label, is_viol = distance_score(mod, tgt, layer_rank)
        vol, vol_label = volatility_score(counts.get(abspaths.get(tgt, ""), 0))
        bal = balance_score(e["strength"], dist, vol)
        issue = detect_issue(e["strength"], dist, vol, is_viol)
        result[(mod, tgt)] = {
            "src": mod, "tgt": tgt,
            "strength": e["strength"], "strength_label": e["strength_label"],
            "distance": dist, "distance_label": dist_label,
            "volatility": vol, "volatility_label": vol_label,
            "balance": bal,
            "severity": issue[0] if issue else None,
            "issue": issue[1] if issue else None,
        }
    return result


def _should_skip(absph, target_abs, exclude_dirs, include_tests):
    rel_parts = set(os.path.relpath(absph, target_abs).split(os.sep))
    skip = set(_BUILTIN_SKIP) | set(exclude_dirs)
    if not include_tests:
        skip |= {"tests", "test"}
        if _is_test_file(os.path.basename(absph)):
            return True
    return bool(rel_parts & skip)


def analyze_diff(target: str, ref: str | None = None) -> dict:
    root = git_root(target)
    if root is None:
        return {"error": "not a git repository"}
    base = ref or "HEAD"

    cfg = load_config(target)
    layer_rank = cfg["layer_rank"]
    exclude_dirs, include_tests = cfg["exclude_dirs"], cfg["include_tests"]

    project_root = discover_project_root(target)
    target_abs = os.path.abspath(target)

    # internal module set + module->abspath, from the current working tree (cheap: no parsing)
    files = list(iter_py_files(target, include_tests=include_tests, exclude_dirs=exclude_dirs))
    abspaths = {module_name(f, project_root): os.path.abspath(f) for f in files}
    internal = set(abspaths)
    counts, _ = commit_counts(target)

    new_issues, regressions, god_changes = [], [], []
    analyzed, before_sum, after_sum, n_before, n_after = [], 0.0, 0.0, 0, 0

    for gitrel in _changed_paths(root, ref):
        absph = os.path.normpath(os.path.join(root, gitrel))
        if absph != target_abs and not absph.startswith(target_abs + os.sep):
            continue  # outside the analyzed package
        if _should_skip(absph, target_abs, exclude_dirs, include_tests):
            continue

        mod = module_name(absph, project_root)
        is_package = gitrel.endswith("__init__.py")
        before_tree = _parse(_content_at(root, base, gitrel))
        after_src = None
        if os.path.exists(absph):
            with open(absph, encoding="utf-8", errors="replace") as fh:
                after_src = fh.read()
        after_tree = _parse(after_src)
        analyzed.append(mod)

        before = _edge_map(mod, before_tree, internal, is_package, layer_rank, counts, abspaths)
        after = _edge_map(mod, after_tree, internal, is_package, layer_rank, counts, abspaths)

        for key, e in after.items():
            b = before.get(key)
            b_sev = b["severity"] if b else None
            if e["severity"] and _SEV_RANK[e["severity"]] > _SEV_RANK[b_sev]:
                new_issues.append(e)
            if b and e["balance"] < b["balance"] - 1e-9:
                regressions.append({**e, "balance_before": b["balance"]})

        before_sum += sum(x["balance"] for x in before.values())
        after_sum += sum(x["balance"] for x in after.values())
        n_before += len(before)
        n_after += len(after)

        gb = {g["class_name"]: g for g in god_in_tree(mod, before_tree)}
        for g in god_in_tree(mod, after_tree):
            prev = gb.get(g["class_name"])
            if prev is None:
                god_changes.append({**g, "change": "new"})
            elif g["cohesion_components"] > prev["cohesion_components"]:
                god_changes.append({**g, "change": "worsened",
                                    "components_before": prev["cohesion_components"]})

    new_critical = sum(1 for e in new_issues if e["severity"] == "critical")
    new_high = sum(1 for e in new_issues if e["severity"] == "high")
    return {
        "base": base,
        "changed_files": len(analyzed),
        "new_critical": new_critical,
        "new_high": new_high,
        "new_issues": new_issues,
        "regressions": sorted(regressions, key=lambda e: e["balance"] - e["balance_before"]),
        "god_changes": god_changes,
        "balance_before": round(before_sum / n_before, 3) if n_before else None,
        "balance_after": round(after_sum / n_after, 3) if n_after else None,
    }
