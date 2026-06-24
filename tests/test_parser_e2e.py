"""End-to-end: build a synthetic Django-shaped package and analyze it."""
import os

from django_coupling.parser import build_graph
from django_coupling.cli import analyze


FILES = {
    "api/__init__.py": "",
    "api/models/__init__.py": "",
    "api/models/budget.py": "class Budget:\n    _secret = 1\n",
    "api/services/__init__.py": "",
    # functional call AND intrusive access on the imported name -> intrusive wins.
    # NB: v0 detects private access on the imported symbol directly (Budget._secret),
    # not on an instance (b = Budget(); b._secret) — that needs data-flow.
    "api/services/budget.py": (
        "from api.models.budget import Budget\n"
        "def run():\n"
        "    Budget()\n"
        "    return Budget._secret\n"
    ),
    "api/views/__init__.py": "",
    # forward-layer: view -> service, plain function call
    "api/views/budget.py": (
        "from api.services import budget\n"
        "def handle():\n"
        "    return budget.run()\n"
    ),
    # reverse-flow: model -> view (architectural violation)
    "api/models/bad.py": (
        "from api.views.budget import handle\n"
        "X = handle\n"
    ),
}


def _make_project(tmp_path):
    root = tmp_path / "proj"
    for rel, content in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return str(root / "api")


def _edge(edges, src, tgt):
    return next((e for e in edges if e["src"] == src and e["tgt"] == tgt), None)


def test_build_graph_resolves_and_scores_strength(tmp_path):
    target = _make_project(tmp_path)
    modules, edges = build_graph(target)
    assert "api.services.budget" in modules
    assert "api.models.budget" in modules

    # intrusive access to Budget._secret dominates -> strength 1.0
    e = _edge(edges, "api.services.budget", "api.models.budget")
    assert e is not None and e["strength"] == 1.0

    # view -> service is a plain call -> functional
    e = _edge(edges, "api.views.budget", "api.services.budget")
    assert e is not None and e["strength"] == 0.75


def test_analyze_flags_layer_violation(tmp_path):
    target = _make_project(tmp_path)
    rep = analyze(target)
    violations = [e for e in rep["edges"]
                  if e["src"] == "api.models.bad" and e["tgt"] == "api.views.budget"]
    assert len(violations) == 1
    assert violations[0]["severity"] == "critical"
    assert violations[0]["issue"] == "layer_violation"
    assert rep["criticals"] >= 1
    assert rep["grade"] in {"D", "F"}
