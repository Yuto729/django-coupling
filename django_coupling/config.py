"""Project configuration via `.coupling.toml`.

Discovered by walking up from the analysis target. Supported sections:

    [layers]
    # name = rank   (smaller rank = higher layer)
    views = 0
    serializers = 2   # same rank as services -> services<->serializers is same-layer
    services = 2
    models = 3

    [analysis]
    # directory names to skip during file discovery, on top of the built-in set
    # (__pycache__, migrations, node_modules, venv, .venv, tests/test)
    exclude_dirs = ["seeds_csv", "seeds_json", "generated"]
    include_tests = false   # set true to analyze test files too

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


def load_config(target: str) -> dict:
    """Load full config. Keys: layer_rank, exclude_dirs, include_tests, path."""
    cfg = {
        "layer_rank": dict(DEFAULT_LAYER_RANK),
        "exclude_dirs": set(),
        "include_tests": False,
        "path": None,
    }
    path = find_config(target)
    if path is None:
        return cfg
    cfg["path"] = path
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        cfg["path"] = None
        return cfg

    layers = data.get("layers")
    if isinstance(layers, dict) and layers:
        rank = {name: int(r) for name, r in layers.items() if isinstance(r, int)}
        if rank:
            cfg["layer_rank"] = rank

    analysis = data.get("analysis")
    if isinstance(analysis, dict):
        excl = analysis.get("exclude_dirs")
        if isinstance(excl, list):
            cfg["exclude_dirs"] = {str(d) for d in excl if isinstance(d, str)}
        if isinstance(analysis.get("include_tests"), bool):
            cfg["include_tests"] = analysis["include_tests"]
    return cfg


def load_layer_rank(target: str) -> tuple[dict, str | None]:
    """Backward-compatible helper: (layer_rank, config_path)."""
    cfg = load_config(target)
    return cfg["layer_rank"], cfg["path"]
