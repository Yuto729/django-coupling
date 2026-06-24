"""Balance Score and health grading.

Balance Score combines the three dimensions following cargo-coupling:

    alignment         = 1.0 - |strength - (1.0 - distance)|
    volatility_impact = 1.0 - (volatility * strength)
    balance           = alignment * volatility_impact     # 0.0-1.0, higher is healthier

Intuition: strong coupling is acceptable when distance is small (alignment high),
and the volatility term punishes strong coupling to things that change a lot.
"""
from __future__ import annotations


def balance_score(strength: float, distance: float, volatility: float) -> float:
    alignment = 1.0 - abs(strength - (1.0 - distance))
    volatility_impact = 1.0 - (volatility * strength)
    return round(alignment * volatility_impact, 4)


# Thresholds for the v0 issue detectors.
STRONG = 0.75
FAR = 0.50
VOLATILE = 0.75


def detect_issue(strength: float, distance: float, volatility: float,
                 is_layer_violation: bool) -> tuple[str, str] | None:
    """Return (severity, kind) for an edge, or None.

    v0 detects exactly two things — the ones git history actually buys us:
      - layer_violation : reverse-flow import (critical)
      - cascading_change: strong + volatile coupling that will ripple (high)
    """
    if is_layer_violation:
        return ("critical", "layer_violation")
    if strength >= STRONG and volatility >= VOLATILE and distance >= FAR:
        return ("high", "cascading_change")
    return None


def grade(avg_balance: float, criticals: int, highs: int) -> str:
    """A coarse S-F grade. Heuristic; thresholds will be tuned post-v0."""
    if criticals > 3:
        return "F"
    if criticals >= 1:
        return "D"
    if avg_balance < 0.5 or highs > 5:
        return "C"
    if avg_balance < 0.7:
        return "B"
    if avg_balance < 0.9:
        return "A"
    return "S"  # warning: possibly over-engineered / over-decoupled
