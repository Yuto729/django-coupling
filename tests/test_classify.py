from django_coupling.classify import (
    strength_from_usages, distance_score, volatility_score,
)


def test_strength_strongest_wins():
    assert strength_from_usages([]) == (0.25, "contract")
    assert strength_from_usages(["model", "functional"]) == (0.75, "functional")
    assert strength_from_usages(["functional", "intrusive"]) == (1.0, "intrusive")
    assert strength_from_usages(["contract"]) == (0.25, "contract")


def test_distance_same_package_is_closest():
    # same containing package (api.services) -> closest
    score, label, viol = distance_score("api.services.budget", "api.services.cost")
    assert (score, label, viol) == (0.25, "same_package", False)


def test_distance_same_layer_different_package():
    # both under the services layer but different sub-packages
    score, label, viol = distance_score("api.services.dash.a", "api.services.cost.b")
    assert score == 0.50 and label == "same_layer" and viol is False


def test_distance_forward_layer_is_ok():
    # views importing services is the expected direction
    score, label, viol = distance_score("api.views.budget", "api.services.budget")
    assert label == "forward_layer" and viol is False


def test_distance_layer_violation_is_flagged():
    # models importing views is reverse-flow -> violation
    score, label, viol = distance_score("api.models.budget", "api.views.budget")
    assert score == 1.0 and label == "layer_violation" and viol is True


def test_distance_cross_top():
    score, label, viol = distance_score("api.services.x", "tasks.jobs.y")
    assert score == 1.0 and label == "cross_top"


def test_volatility_thresholds():
    assert volatility_score(0) == (0.0, "low")
    assert volatility_score(2) == (0.0, "low")
    assert volatility_score(3) == (0.5, "medium")
    assert volatility_score(10) == (0.5, "medium")
    assert volatility_score(11) == (1.0, "high")
