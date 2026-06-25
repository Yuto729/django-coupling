from django_coupling.score import balance_score, detect_issue, grade


def test_balance_strong_close_is_high():
    # strong coupling (1.0) but very close (distance 0.0) and stable -> aligned
    assert balance_score(1.0, 0.0, 0.0) == 1.0


def test_balance_strong_far_is_low():
    # strong coupling across a large distance -> misaligned
    assert balance_score(1.0, 1.0, 0.0) == 0.0


def test_balance_volatility_punishes_strong():
    stable = balance_score(1.0, 0.0, 0.0)
    volatile = balance_score(1.0, 0.0, 1.0)
    assert volatile < stable


def test_detect_layer_violation_is_critical():
    assert detect_issue(0.5, 1.0, 0.0, True) == ("critical", "layer_violation")


def test_detect_cascading_change():
    assert detect_issue(0.75, 0.5, 0.75, False) == ("high", "cascading_change")


def test_detect_none_when_balanced():
    assert detect_issue(1.0, 0.25, 0.0, False) is None


def test_grade_critical_drops_to_d_or_f():
    assert grade(0.9, criticals=1, highs=0) == "D"
    assert grade(0.9, criticals=4, highs=0) == "F"


def test_grade_healthy():
    assert grade(0.95, 0, 0) == "S"
    assert grade(0.8, 0, 0) == "A"
