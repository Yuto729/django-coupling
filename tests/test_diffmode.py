import subprocess

from django_coupling.diffmode import analyze_diff


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "api" / "models").mkdir(parents=True)
    (repo / "api" / "services").mkdir(parents=True)
    (repo / "api" / "__init__.py").write_text("")
    (repo / "api" / "models" / "__init__.py").write_text("")
    (repo / "api" / "services" / "__init__.py").write_text("")
    (repo / "api" / "models" / "cost.py").write_text(
        "class Cost:\n    _raw = 1\n    def total(self): return 1\n"
    )
    # baseline: services.cost uses models.cost via a plain function call (functional)
    (repo / "api" / "services" / "cost.py").write_text(
        "from api.models import cost\n"
        "def total():\n"
        "    return cost.Cost().total()\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    return repo


def test_diff_detects_strength_regression(tmp_path):
    repo = _make_repo(tmp_path)
    # working-tree change: now reaches into a private member -> intrusive (strength up)
    (repo / "api" / "services" / "cost.py").write_text(
        "from api.models import cost\n"
        "def total():\n"
        "    return cost.Cost._raw\n"
    )
    rep = analyze_diff(str(repo / "api"))  # working tree vs HEAD
    assert rep["changed_files"] == 1
    regr = [r for r in rep["regressions"]
            if r["src"] == "api.services.cost" and r["tgt"] == "api.models.cost"]
    assert len(regr) == 1
    assert regr[0]["balance"] < regr[0]["balance_before"]
    assert regr[0]["strength_label"] == "intrusive"


def test_diff_flags_new_layer_violation_and_exit(tmp_path):
    repo = _make_repo(tmp_path)
    # add a serializers layer and make models.cost import it -> reverse-flow (critical)
    (repo / "api" / "serializers").mkdir()
    (repo / "api" / "serializers" / "__init__.py").write_text("")
    (repo / "api" / "serializers" / "cost.py").write_text("X = 1\n")
    (repo / "api" / "models" / "cost.py").write_text(
        "from api.serializers import cost as s\n"
        "class Cost:\n    def total(self): return s.X\n"
    )
    rep = analyze_diff(str(repo / "api"))
    violations = [e for e in rep["new_issues"] if e["issue"] == "layer_violation"]
    assert any(e["src"] == "api.models.cost" and e["tgt"] == "api.serializers.cost"
               for e in violations)
    assert rep["new_critical"] >= 1


def test_diff_clean_when_no_changes(tmp_path):
    repo = _make_repo(tmp_path)
    rep = analyze_diff(str(repo / "api"))
    assert rep["changed_files"] == 0
    assert rep["new_issues"] == [] and rep["regressions"] == []


def test_diff_non_git_returns_error(tmp_path):
    (tmp_path / "api").mkdir()
    rep = analyze_diff(str(tmp_path / "api"))
    assert "error" in rep
