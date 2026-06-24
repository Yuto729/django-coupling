"""Project configuration via `.coupling.toml`.

Discovered by walking up from the analysis target. v0 supports one section:

    [layers]
    # name = rank   (smaller rank = higher layer)
    views = 0
    serializers = 2   # same rank as services -> services<->serializers is same-layer
    services = 2
    models = 3

Read-only TOML via stdlib `tomllib` (Python 3.11+); zero third-party deps.
"""
from __future__ import annotations

import os
import tomllib

from .classify import DEFAULT_LAYER_RANK

CONFIG_NAME = ".coupling.toml"


def find_config(target: str) -> str | None:
    """Walk up from `target` looking for .coupling.toml."""
    cur = os.path.abspath(target)
    if os.path.isfile(cur):
        cur = os.path.dirname(cur)
    while True:
        candidate = os.path.join(cur, CONFIG_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_layer_rank(target: str) -> tuple[dict, str | None]:
    """Return (layer_rank, config_path). Falls back to defaults if absent/invalid."""
    path = find_config(target)
    if path is None:
        return dict(DEFAULT_LAYER_RANK), None
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return dict(DEFAULT_LAYER_RANK), None

    layers = data.get("layers")
    if not isinstance(layers, dict) or not layers:
        return dict(DEFAULT_LAYER_RANK), path
    rank = {name: int(r) for name, r in layers.items() if isinstance(r, int)}
    if not rank:
        return dict(DEFAULT_LAYER_RANK), path
    return rank, path
