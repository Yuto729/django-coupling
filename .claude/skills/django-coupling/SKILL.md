---
name: django-coupling
description: Reference for the django-coupling CLI — a static coupling analyzer for Django/Python codebases. Use when analyzing architecture or coupling of a Python/Django project, locating layer violations or cascading-change risks, finding God-class or file-split candidates, or interpreting django-coupling's text/JSON output. Not for analyzing non-Python code.
---

# django-coupling — reference

`django-coupling` is a static-analysis CLI. It builds a module-level import
graph for a Python/Django package and scores each dependency along three
dimensions (Strength × Distance × Volatility), plus a separate class-level
God-class pass. It is a measurement aid; its outputs are signals for review,
not verdicts. It does not modify code.

## When this applies

- Assessing coupling / architectural health of a Python or Django package.
- Locating layer violations (e.g. `models` importing `views`), cascading-change
  risks, God-class candidates, or files that should be split.
- Interpreting an existing django-coupling report (text or `--json`).

When it does not apply: non-Python codebases; questions answerable by reading a
single file; runtime/behavioral analysis (this is static only).

## Running it

```bash
# from a clone / installed env
django-coupling <path-to-package>

# via Nix from GitHub
nix run github:Yuto729/django-coupling -- <path-to-package>
```

`<path-to-package>` is the package directory to analyze (e.g. a Django app's
`api/` directory), not necessarily the repo root. The tool resolves dotted
module names relative to the parent of the top-most package.

### Help

```bash
django-coupling --help
```

```
positional arguments:
  path                  package/directory to analyze
options:
  --json                emit machine-readable JSON
  --top TOP             how many rows to show (default 15)
  --since SINCE         git window for volatility (e.g. "3 months ago")
  --max-commit-files N  exclude commits touching more than N files from
                        volatility (default 30)
  --god-min-methods N   min instance methods for a class to be a God candidate
                        (default 4)
```

Prefer `--json` for programmatic consumption; it contains the full edge list and
all metrics. The text output shows only the top-N rows per section.

## The scoring model

Each dependency edge `A -> B` (A imports/uses B) gets three 0.0–1.0 scores:

- **strength** — how deeply A reaches into B (from static AST usage):
  `contract` 0.25 (type annotation / base class only) <
  `model` 0.50 (references a shared symbol) <
  `functional` 0.75 (calls a function/method) <
  `intrusive` 1.00 (touches a private/internal member). Strongest usage wins.
- **distance** — structural separation with Django layer direction:
  `same_package` 0.25; `same_layer` / `forward_layer` 0.50;
  `cross_top` / `layer_violation` 1.00. Layer order is
  `views > serializers > services > models`; a lower layer importing a higher
  one is `layer_violation`. The ranking is configurable (see `.coupling.toml`).
- **volatility** — how often B changes, from git commit counts in `--since`:
  0–2 commits → 0.0 (low), 3–10 → 0.5 (medium), 11+ → 1.0 (high).

Combined:

```
balance = (1 - |strength - (1 - distance)|) * (1 - volatility * strength)
```

Range 0.0–1.0, **higher is healthier**. Intuition: strong coupling is fine when
distance is small; the volatility term penalizes strong coupling to things that
change a lot. Low balance = strong + far, and/or strong + volatile.

## Interpreting the output

### Summary line
- `Grade` (S–F): coarse overall health. `F` = >3 critical issues; `D` = ≥1
  critical; `C` = avg balance <0.5 or >5 high issues; `B` <0.7; `A` <0.9;
  `S` ≥0.9. **`S` is a warning of possible over-decoupling, not praise.**
- `average balance score`: mean balance across all edges.
- `critical issues` / `high issues`: counts by severity.

### volatility confidence
`high` / `medium` / `low`, derived from the repo's commit-size distribution.
**Treat the volatility dimension as less reliable when this is `medium`/`low`**
(large, mixed commits make per-file change counts noisy). If git history is
unavailable, volatility defaults to 0 and a warning is printed.

### Issues
Detected problems, by severity:
- `layer_violation` (critical) — a lower layer imports a higher one
  (reverse-flow). Whether this is truly wrong depends on the project's intended
  layering, which is configurable.
- `cascading_change` (high) — strong (≥0.75) + far (distance ≥0.5) + volatile
  (≥0.75): a change-propagation risk.

### Hotspots
Lowest-balance edges, with the three dimensions broken out. Use to see *why* an
edge is unhealthy (e.g. `strength=1.00 (intrusive)` + `volatility=1.00 (high)`).

### God class candidates (class granularity)
Each entry: `cohesion_components` (LCOM4 — connected components of the method
graph; ≥2 means the class splits into unrelated method clusters), `methods`,
`instance_fields`, `distinct_imports_used` (class-level fan-out),
`module_god_count` (how many candidates share the same file).

- These are **candidates for human/AI review, not verdicts.** Framework classes
  (DRF ViewSets, Django Admin, FilterSets) and rich models can score high
  legitimately. Confirm by reading the source before acting.
- A file with `module_god_count ≥ 2` plus a high `module_summary` fan-out is a
  reasonable file-split candidate — verify against the source.
- Tests are excluded by default; instance-level intrusive access
  (`obj = X(); obj._y`) is **not** detected (no data-flow analysis).

### Module summary (per-file rollup)
Per module: `efferent_edges` (outgoing dependencies), `afferent_edges`
(incoming), `distinct_target_packages`, `mean_distance`, `god_candidates`.
High efferent + many distinct target packages + multiple god candidates suggests
a file mixing concerns (split candidate). Note: re-export `__init__.py`
aggregators legitimately show high afferent/efferent — not a smell.

## JSON schema (`--json`)

```
target, config, layer_rank, git_available,
volatility_diagnostics{commits, median_files, p90_files, excluded_bulk,
                        max_commit_files, confidence, ...},
module_count, edge_count, avg_balance, grade, criticals, highs,
edges[{src, tgt, strength, strength_label, distance, distance_label,
       volatility, volatility_label, commits, balance, severity, issue}],
god_candidates[{module, class_name, methods, instance_fields,
                cohesion_components, distinct_imports_used,
                module_god_count, severity}],
module_summary[{module, efferent_edges, afferent_edges,
                distinct_target_packages, mean_distance, god_candidates}]
```

`edges` is the complete edge list; derive any per-module aggregation from it if
`module_summary` doesn't cover the needed view.

## Configuration

`.coupling.toml` is discovered by walking up from the analyzed path:

```toml
[layers]
# name = rank (smaller = higher layer); equal ranks => same-layer (no violation)
views = 0
serializers = 2
services = 2
models = 3

[analysis]
exclude_dirs = ["seeds_csv", "generated"]   # added to built-in skip set
include_tests = false
```

The default layer ranking flags `services -> serializers` as a violation; this
is opinionated and project-dependent. Check whether a `.coupling.toml` is in
effect (the `config:` line / `config` JSON key) before treating layer violations
as definitive.

## Limitations to account for

- Static analysis only: macros, dynamic imports, getattr, runtime dispatch are
  invisible. Only intra-project edges are scored (third-party imports excluded).
- Strength is approximated from syntactic usage; instance-level private access
  is undercounted.
- Volatility depends on git history quality (see confidence).
- God-class and layer-violation results include framework/architecture-dependent
  false positives. All outputs are starting points for review, not conclusions.
