"""God-class detection at class granularity.

Module-level coupling can't see a 1000-line class inside one file, so this works
on `ast.ClassDef` nodes directly.

The signal is **cohesion, not size** — size conflates "large but cohesive" with
"does everything". We use LCOM4: model a class as a graph where methods are nodes
and two methods are linked when they touch a common `self.*` member (a shared
field, or one calling the other). The number of connected components is
size-independent:

    cohesive class (any size) -> all methods reachable via shared state -> 1 component
    god class                 -> splits into unrelated method clusters   -> >=2 components

A class that decomposes into >=2 components is literally several classes wearing
one name. fan-out (how many distinct imported names the class touches) is a
secondary severity signal. Output is *candidates for review*, never a verdict —
facades / DTOs / Django models can score high legitimately.

Deliberately git-free: co-change is too polluted by large AI-era commits to
trust here (see volatility.py).
"""
from __future__ import annotations

import ast
import os
from collections import Counter

from .parser import discover_project_root, iter_py_files, module_name

DEFAULT_MIN_METHODS = 4


def _instance_methods(classnode: ast.ClassDef) -> list[ast.AST]:
    """Methods defined directly in the class body, excluding @staticmethod."""
    out = []
    for item in classnode.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decos = {d.id for d in item.decorator_list if isinstance(d, ast.Name)}
            if "staticmethod" in decos:
                continue  # no self -> not part of the cohesion graph
            out.append(item)
    return out


def _self_members(funcnode: ast.AST) -> set[str]:
    """Names accessed via the first parameter (self/cls): self.<member>."""
    args = funcnode.args.posonlyargs + funcnode.args.args
    if not args:
        return set()
    selfname = args[0].arg
    members = set()
    for n in ast.walk(funcnode):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == selfname):
            members.add(n.attr)
    return members


def lcom4(methods: list[ast.AST]) -> int:
    """Number of connected components of the method-cohesion graph."""
    names = [m.name for m in methods]
    members = [_self_members(m) for m in methods]
    parent = list(range(len(methods)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(methods)):
        for j in range(i + 1, len(methods)):
            # linked if they share a self-member, or one calls/refers to the other
            if (members[i] & members[j]
                    or names[j] in members[i] or names[i] in members[j]):
                union(i, j)
    return len({find(i) for i in range(len(methods))})


def _self_fields(classnode: ast.ClassDef) -> set[str]:
    """Instance fields assigned via `self.<name> = ...` anywhere in the class.

    LCOM cohesion is only meaningful when a class has shared state. A class with
    zero instance fields (Django Admin/FilterSet hooks, pure-function bags) reads
    as maximally incohesive by construction — not a God class in the OO sense — so
    we use field count as a candidacy gate, not just a metric.
    """
    fields = set()
    for n in ast.walk(classnode):
        targets = []
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            targets = [n.target]
        for t in targets:
            if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id in ("self", "cls")):
                fields.add(t.attr)
    return fields


def _bound_import_names(tree: ast.AST) -> set[str]:
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                names.add(a.asname or a.name)
    return names


def _fan_out(classnode: ast.ClassDef, bound: set[str]) -> int:
    """Distinct imported names referenced anywhere in the class."""
    used = set()
    for n in ast.walk(classnode):
        if isinstance(n, ast.Name) and n.id in bound:
            used.add(n.id)
    return len(used)


def god_in_tree(mod: str, tree, min_methods: int = DEFAULT_MIN_METHODS) -> list[dict]:
    """God-class candidates in a single module's AST (no module_god_count).

    Used both by find_god_classes (whole project) and diff mode (one file).
    """
    if tree is None:
        return []
    bound = _bound_import_names(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = _instance_methods(node)
        if len(methods) < min_methods:
            continue
        fields = _self_fields(node)
        if not fields:
            continue  # no shared state -> LCOM4 meaningless (framework/util bag)
        components = lcom4(methods)
        if components < 2:
            continue  # cohesive -> not a candidate
        # all-singletons (lcom4 == methods) is a stateless bag, not OO god-class
        if components >= len(methods):
            continue
        fan = _fan_out(node, bound)
        severity = "high" if (components >= 3 or fan >= 10) else "medium"
        out.append({
            "module": mod,
            "class_name": node.name,
            "methods": len(methods),
            "instance_fields": len(fields),
            "cohesion_components": components,   # LCOM4
            "distinct_imports_used": fan,        # class-level efferent fan-out
            "severity": severity,
        })
    return out


def find_god_classes(target: str, min_methods: int = DEFAULT_MIN_METHODS,
                     include_tests: bool = False, exclude_dirs=None) -> list[dict]:
    """Return God-class candidates, strongest first."""
    root = discover_project_root(target)
    results = []
    for path in iter_py_files(target, include_tests=include_tests, exclude_dirs=exclude_dirs):
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        results.extend(god_in_tree(module_name(path, root), tree, min_methods))
    # annotate how many God candidates live in the same file (a split signal)
    per_module = Counter(r["module"] for r in results)
    for r in results:
        r["module_god_count"] = per_module[r["module"]]
    results.sort(key=lambda r: (r["severity"] != "high",
                                -r["cohesion_components"], -r["methods"]))
    return results
