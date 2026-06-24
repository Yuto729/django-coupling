"""Static import-graph extraction via the `ast` module.

Walks a package, resolves intra-project imports to module nodes, and classifies
how each imported symbol is *used* (to derive Integration Strength).
"""
from __future__ import annotations

import ast
import os

from .classify import strength_from_usages


# --- module / path helpers ------------------------------------------------
def discover_project_root(target: str) -> str:
    """Given a target dir, return the dir to resolve absolute imports against.

    If `target` is a package (has __init__.py), climb to the top-most package
    and return its parent — so a file's dotted module name is its path relative
    to that root (e.g. .../smbkikan-back/api/services/budget.py -> api.services.budget).
    """
    target = os.path.abspath(target)
    if not os.path.isfile(os.path.join(target, "__init__.py")):
        return target
    top = target
    while os.path.isfile(os.path.join(os.path.dirname(top), "__init__.py")):
        top = os.path.dirname(top)
    return os.path.dirname(top)


def module_name(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    rel = rel[:-3] if rel.endswith(".py") else rel
    parts = [p for p in rel.split(os.sep) if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_test_file(fn: str) -> bool:
    return (fn.startswith("test_") or fn.endswith("_test.py")
            or fn in {"conftest.py", "tests.py"})


def iter_py_files(target: str, include_tests: bool = False):
    for dirpath, dirnames, filenames in os.walk(target):
        # skip virtualenvs, migrations, caches, hidden dirs (and tests by default,
        # matching cargo-coupling: test->internal coupling is expected, not a smell)
        skip_dirs = {"__pycache__", "migrations", "node_modules", "venv", ".venv"}
        if not include_tests:
            skip_dirs |= {"tests", "test"}
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and not d.startswith(".")
        ]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            if not include_tests and _is_test_file(fn):
                continue
            yield os.path.join(dirpath, fn)


# --- usage classification -------------------------------------------------
class _UsageVisitor(ast.NodeVisitor):
    """For each bound import name, collect the set of usage kinds seen."""

    def __init__(self, bound: dict[str, set[str]]):
        # bound: local name -> set of target modules it may refer to
        self.bound = bound
        self.kinds: dict[str, set[str]] = {m: set() for ms in bound.values() for m in ms}
        self._type_pos: set[int] = set()  # id() of nodes in annotation/base position

    # -- record type positions first (annotations, base classes) --
    def _mark_type_positions(self, node):
        for sub in ast.walk(node):
            self._type_pos.add(id(sub))

    def _root_name(self, node):
        """Leftmost Name id of an attribute/name chain, else None."""
        while isinstance(node, ast.Attribute):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    def _emit(self, name: str | None, kind: str):
        if name is None or name not in self.bound:
            return
        for mod in self.bound[name]:
            self.kinds[mod].add(kind)

    def visit_ClassDef(self, node):
        for base in node.bases:
            self._mark_type_positions(base)
            self._emit(self._root_name(base), "contract")
        for kw in node.keywords:  # metaclass=, etc.
            self._mark_type_positions(kw.value)
        self.generic_visit(node)

    def _visit_annotation(self, ann):
        if ann is not None:
            self._mark_type_positions(ann)
            self._emit(self._root_name(ann), "contract")

    def visit_AnnAssign(self, node):
        self._visit_annotation(node.annotation)
        self.generic_visit(node)

    def visit_arg(self, node):
        self._visit_annotation(node.annotation)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._visit_annotation(node.returns)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        self._emit(self._root_name(node.func), "functional")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith("_"):
            self._emit(self._root_name(node), "intrusive")
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            kind = "contract" if id(node) in self._type_pos else "model"
            self._emit(node.id, kind)
        self.generic_visit(node)


# --- import resolution ----------------------------------------------------
def _resolve_imports(tree: ast.AST, current_module: str, is_package: bool,
                     internal: set[str]) -> dict[str, set[str]]:
    """Return: local bound name -> set of resolved internal target modules."""
    bound: dict[str, set[str]] = {}

    if is_package:
        cur_pkg_parts = current_module.split(".")
    else:
        cur_pkg_parts = current_module.split(".")[:-1]

    def add(name: str, target: str):
        if target in internal:
            bound.setdefault(name, set()).add(target)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name  # full dotted, e.g. api.services.budget
                local = alias.asname or alias.name.split(".")[0]
                # match the longest internal prefix of the dotted target
                parts = target.split(".")
                for i in range(len(parts), 0, -1):
                    cand = ".".join(parts[:i])
                    if cand in internal:
                        add(local, cand)
                        break
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base_parts = cur_pkg_parts[: len(cur_pkg_parts) - (node.level - 1)]
                prefix = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            if not prefix:
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                submodule = f"{prefix}.{alias.name}"
                # prefer importing a submodule; fall back to a symbol in `prefix`
                if submodule in internal:
                    add(local, submodule)
                elif prefix in internal:
                    add(local, prefix)
    return bound


# --- public API -----------------------------------------------------------
def build_graph(target: str):
    """Parse `target` and return (modules, edges).

    modules: dict module_name -> relative file path
    edges:   list of dicts {src, tgt, strength, strength_label}
    """
    root = discover_project_root(target)
    files = list(iter_py_files(target))
    modules = {module_name(f, root): f for f in files}
    internal = set(modules)

    edges = []
    for mod, path in modules.items():
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        is_package = path.endswith(os.sep + "__init__.py") or path.endswith("/__init__.py")
        bound = _resolve_imports(tree, mod, is_package, internal)
        if not bound:
            continue
        visitor = _UsageVisitor(bound)
        visitor.visit(tree)
        for tgt, kinds in visitor.kinds.items():
            if tgt == mod:
                continue  # ignore self-references
            score, label = strength_from_usages(kinds)
            edges.append({"src": mod, "tgt": tgt, "strength": score, "strength_label": label})
    return modules, edges
