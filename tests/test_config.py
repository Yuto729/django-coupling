from django_coupling.classify import distance_score, DEFAULT_LAYER_RANK
from django_coupling.config import load_layer_rank, load_config, find_config
from django_coupling.parser import build_graph


def test_defaults_when_no_config(tmp_path):
    rank, path = load_layer_rank(str(tmp_path))
    assert path is None
    assert rank == DEFAULT_LAYER_RANK


def test_loads_layers_section(tmp_path):
    (tmp_path / ".coupling.toml").write_text(
        "[layers]\nviews = 0\nservices = 2\nserializers = 2\nmodels = 3\n"
    )
    rank, path = load_layer_rank(str(tmp_path))
    assert path is not None
    assert rank == {"views": 0, "services": 2, "serializers": 2, "models": 3}


def test_config_discovered_walking_up(tmp_path):
    (tmp_path / ".coupling.toml").write_text("[layers]\nviews = 0\n")
    nested = tmp_path / "api" / "services"
    nested.mkdir(parents=True)
    assert find_config(str(nested)) == str(tmp_path / ".coupling.toml")


def test_analysis_exclude_dirs_loaded(tmp_path):
    (tmp_path / ".coupling.toml").write_text(
        "[analysis]\nexclude_dirs = [\"seeds\", \"generated\"]\ninclude_tests = true\n"
    )
    cfg = load_config(str(tmp_path))
    assert cfg["exclude_dirs"] == {"seeds", "generated"}
    assert cfg["include_tests"] is True


def test_build_graph_honors_exclude_dirs(tmp_path):
    root = tmp_path / "proj"
    for rel in ["api/__init__.py", "api/services/__init__.py",
                "api/services/budget.py", "api/seeds/__init__.py", "api/seeds/data.py"]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("X = 1\n")
    modules, _ = build_graph(str(root / "api"), exclude_dirs={"seeds"})
    assert "api.services.budget" in modules
    assert "api.seeds.data" not in modules


def test_custom_rank_makes_services_serializers_same_layer():
    default = distance_score("api.services.x", "api.serializers.x")
    assert default[2] is True  # violation under defaults

    same_rank = {"views": 0, "services": 2, "serializers": 2, "models": 3}
    score, label, viol = distance_score("api.services.x", "api.serializers.x", same_rank)
    assert viol is False and label == "same_layer"
