"""Classification of the three coupling dimensions into 0.0-1.0 scores.

Pure functions, no I/O — this is the unit-tested core.
"""
from __future__ import annotations

# --- Integration Strength -------------------------------------------------
# Weakest (interface only) to strongest (reaching into internals).
STRENGTH = {
    "contract": 0.25,   # used only as a type annotation / base class
    "model": 0.50,      # references a shared symbol (constant, model, dataclass)
    "functional": 0.75, # calls a function / method on the imported symbol
    "intrusive": 1.00,  # touches a private/internal member (_x, ._meta, ...)
}


def strength_from_usages(usage_kinds) -> tuple[float, str]:
    """Strongest usage wins (cargo-coupling treats intrusive access as dominant).

    `usage_kinds` is an iterable of keys in STRENGTH. Empty -> contract (a bare
    import with no observed use is, at most, an interface dependency).
    """
    best_label, best_score = "contract", STRENGTH["contract"]
    for kind in usage_kinds:
        score = STRENGTH.get(kind, STRENGTH["contract"])
        if score > best_score:
            best_label, best_score = kind, score
    return best_score, best_label


# --- Distance -------------------------------------------------------------
# Django layer ranks: smaller rank = higher layer. A higher layer importing a
# lower one (views -> services -> models) is the *expected* direction. The
# reverse (models -> views) is an architectural violation.
#
# These are defaults; a project can override them via `[layers]` in
# .coupling.toml (see config.py). e.g. set serializers and services to the same
# rank so `services -> serializers` reads as same-layer rather than a violation.
DEFAULT_LAYER_RANK = {
    "views": 0,
    "serializers": 1,
    "services": 2,
    "selectors": 2,
    "models": 3,
}

# Backwards-compatible alias.
LAYER_RANK = DEFAULT_LAYER_RANK

DISTANCE = {
    "same_package": 0.25,
    "same_layer": 0.50,
    "forward_layer": 0.50,
    "cross_top": 1.00,
    "layer_violation": 1.00,
}


def _split(module: str) -> list[str]:
    return module.split(".")


def _package(module: str) -> str:
    parts = _split(module)
    return ".".join(parts[:-1]) if len(parts) > 1 else module


def _layer(module: str, layer_rank: dict) -> str | None:
    """The Django layer of a module, e.g. api.services.budget -> 'services'."""
    parts = _split(module)
    if len(parts) >= 2 and parts[1] in layer_rank:
        return parts[1]
    return None


def distance_score(src: str, tgt: str, layer_rank: dict | None = None
                   ) -> tuple[float, str, bool]:
    """Return (score, label, is_layer_violation) for an edge src -> tgt.

    `layer_rank` maps a layer name to a rank (smaller = higher layer); defaults
    to DEFAULT_LAYER_RANK and is overridable via .coupling.toml.
    """
    if layer_rank is None:
        layer_rank = DEFAULT_LAYER_RANK
    src_parts, tgt_parts = _split(src), _split(tgt)

    # Different top-level package -> maximally distant.
    if src_parts[0] != tgt_parts[0]:
        return DISTANCE["cross_top"], "cross_top", False

    # Same package (same containing directory) -> closest.
    if _package(src) == _package(tgt):
        return DISTANCE["same_package"], "same_package", False

    src_layer, tgt_layer = _layer(src, layer_rank), _layer(tgt, layer_rank)
    if src_layer is not None and tgt_layer is not None:
        if layer_rank[src_layer] == layer_rank[tgt_layer]:
            return DISTANCE["same_layer"], "same_layer", False
        # Lower rank number = higher layer. Higher importing lower = forward.
        if layer_rank[src_layer] < layer_rank[tgt_layer]:
            return DISTANCE["forward_layer"], "forward_layer", False
        # Lower layer importing a higher one = architectural reverse-flow.
        return DISTANCE["layer_violation"], "layer_violation", True

    # Same top package, layer unknown -> treat as a moderate same-layer-ish gap.
    return DISTANCE["same_layer"], "same_layer", False


# --- Volatility -----------------------------------------------------------
def volatility_score(commit_count: int) -> tuple[float, str]:
    """Map recent commit count (e.g. last 6 months) to a volatility score."""
    if commit_count <= 2:
        return 0.0, "low"
    if commit_count <= 10:
        return 0.5, "medium"
    return 1.0, "high"
