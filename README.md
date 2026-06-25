# django-coupling

Coupling analysis for Django / Python projects — a Python take on
[`cargo-coupling`](https://github.com/nwiizo/cargo-coupling), based on Vlad
Khononov's *Balancing Coupling in Software Design*.

The premise: **coupling is not inherently bad — unbalanced coupling is.** Strong
coupling is fine when the things are close or stable; it hurts when it is strong
*and* far, or strong *and* volatile. The tool externalizes that judgment into a
measurable signal instead of leaving it in a senior engineer's head (a
"fitness function" against cognitive/understanding debt).

## The three dimensions

| Dimension | What it measures | Source |
|---|---|---|
| **Strength** | how tightly a module reaches into another | static `ast` usage |
| **Distance** | structural separation + Django layer direction | module paths |
| **Volatility** | how often the target changes | git history |

```
balance = (1 - |strength - (1 - distance)|) * (1 - volatility * strength)
```
0.0–1.0, higher is healthier. Aggregated into an S–F grade.

### Strength levels
`contract` (0.25, type/base-class only) < `model` (0.50, shared symbol) <
`functional` (0.75, calls) < `intrusive` (1.00, touches `_private` / `._meta`).

### Distance & Django layers
Layer order `views > serializers > services > models`. A higher layer importing
a lower one (`views → services → models`) is the expected direction; the reverse
(`models → views`) is flagged as a **layer violation** (critical). Layers with
the *same* rank are treated as same-layer (no violation either way).

The ranking is the project's call — override it in `.coupling.toml` (discovered
by walking up from the analysis path):

```toml
[layers]
# name = rank (smaller = higher layer). Equal ranks => same-layer.
views = 0
serializers = 2   # same rank as services: services <-> serializers is NOT a violation
services = 2
models = 3

[analysis]
# extra directory names to skip, on top of the built-ins
# (__pycache__, migrations, node_modules, venv, .venv, tests/test)
exclude_dirs = ["seeds_csv", "seeds_json", "generated"]
include_tests = false   # true to analyze test files too
```

> On smbkikan-back, putting `serializers` and `services` at the same rank drops
> critical violations from 74 to 19 — the remaining 19 are genuine reverse-flow.

### Volatility
Commits touching the target file in a recent window (default 6 months):
0–2 → low (0.0), 3–10 → medium (0.5), 11+ → high (1.0).

Git is a noisier sensor in the AI-coding era (one commit can touch many
unrelated files), so the signal is hardened by combining mitigations:

- `--no-merges` (merges aren't real edits)
- commits touching more than `--max-commit-files` (default 30) are **excluded** —
  a single N-file commit would otherwise inflate N files at once
- the tool **self-reports confidence** (`high`/`medium`/`low`) from the repo's
  own commit-size distribution, instead of pretending the signal is always good:

  ```
  volatility confidence: high  (median 2 files/commit, p90 7, 3/923 bulk commits >30 excluded)
  ```

## God-class detection (class granularity)

Module-level coupling can't see a huge class inside one file, so a separate pass
flags **God-class candidates** at `ast.ClassDef` granularity. The signal is
**cohesion, not size** (size can't tell "large but cohesive" from "does
everything"):

- **LCOM4** — methods are graph nodes, linked when they touch a common `self.*`
  member (shared field, or one calling the other). Connected components are
  size-independent: a cohesive class is 1 component at any size; a God class
  splits into ≥2 (literally several classes under one name).
- Candidacy gates (precision over recall — false accusations erode trust):
  - class must have ≥1 instance field (LCOM is undefined without shared state;
    drops Django Admin/FilterSet hooks and pure-function bags)
  - excludes the all-singleton case (stateless method bag, a different smell)
  - tests excluded (test→internal coupling is expected)
- `fan_out` (distinct imports the class touches) is a secondary severity signal.

Output is **candidates for review, never a verdict** — facades, DTOs and rich
Django models can score high legitimately. Deliberately git-free (co-change is
too polluted by large AI-era commits to trust here).

> On smbkikan-back the gates take it from 314 raw → 34 actionable candidates.

## Usage

```bash
django-coupling path/to/package
django-coupling path/to/package --json | jq '.edges[:10]'
django-coupling path/to/package --top 30 --since "3 months ago"
```

Zero runtime dependencies (stdlib `ast` + `git`).

## v0 scope & known limits

This is an MVP (v0). It intentionally does **not** do:

- `--web` visualization, `--baseline` diff gates, `--impact` / `--trace`
- Django ForeignKey / signal coupling (import graph only)
- God-class thresholds (`--god-min-methods`, field/fan-out gates) are heuristic;
  framework-heavy classes (ViewSets, Admin) may still appear as candidates

`.coupling.toml` currently supports only `[layers]`; other thresholds
(`max_dependencies`, etc.) remain hard-coded.

Heuristic limits worth knowing:

- Strength via instances is undercounted — `Budget._x` is detected as intrusive,
  but `b = Budget(); b._x` is not (no data-flow analysis).
- `services → serializers` is flagged as a violation under the default ranking;
  whether that is "wrong" depends on your architecture — override via
  `.coupling.toml` `[layers]`.

Results are guidance, not verdicts — a starting point for human review.

## Development

```bash
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```
