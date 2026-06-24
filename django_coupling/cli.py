"""Command-line entry point: `django-coupling <path> [--json] [--top N] [--since ...]`."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .classify import distance_score, volatility_score
from .parser import build_graph
from .score import balance_score, detect_issue, grade
from .volatility import commit_counts


def analyze(target: str, since: str = "6 months ago") -> dict:
    modules, edges = build_graph(target)
    abspaths = {mod: os.path.abspath(path) for mod, path in modules.items()}
    counts = commit_counts(target, since=since)
    git_available = bool(counts)

    results = []
    for e in edges:
        src, tgt, strength = e["src"], e["tgt"], e["strength"]
        dist, dist_label, is_violation = distance_score(src, tgt)
        n_commits = counts.get(abspaths.get(tgt, ""), 0)
        vol, vol_label = volatility_score(n_commits)
        bal = balance_score(strength, dist, vol)
        issue = detect_issue(strength, dist, vol, is_violation)
        results.append({
            "src": src, "tgt": tgt,
            "strength": strength, "strength_label": e["strength_label"],
            "distance": dist, "distance_label": dist_label,
            "volatility": vol, "volatility_label": vol_label, "commits": n_commits,
            "balance": bal,
            "severity": issue[0] if issue else None,
            "issue": issue[1] if issue else None,
        })

    avg = round(sum(r["balance"] for r in results) / len(results), 4) if results else 1.0
    criticals = sum(1 for r in results if r["severity"] == "critical")
    highs = sum(1 for r in results if r["severity"] == "high")
    return {
        "target": os.path.abspath(target),
        "git_available": git_available,
        "module_count": len(modules),
        "edge_count": len(results),
        "avg_balance": avg,
        "grade": grade(avg, criticals, highs),
        "criticals": criticals,
        "highs": highs,
        "edges": results,
    }


def _render_text(rep: dict, top: int) -> str:
    lines = []
    lines.append(f"django-coupling  {rep['target']}")
    lines.append("=" * 60)
    lines.append(f"Grade: {rep['grade']}   avg balance: {rep['avg_balance']:.3f}")
    lines.append(f"modules: {rep['module_count']}   edges: {rep['edge_count']}"
                 f"   critical: {rep['criticals']}   high: {rep['highs']}")
    if not rep["git_available"]:
        lines.append("(!) git history unavailable — volatility defaulted to 0")
    lines.append("")

    issues = [e for e in rep["edges"] if e["severity"]]
    issues.sort(key=lambda e: (e["severity"] != "critical", e["balance"]))
    if issues:
        lines.append(f"Issues ({len(issues)}):")
        for e in issues[:top]:
            lines.append(
                f"  [{e['severity']:<8}] {e['issue']:<16} "
                f"{e['src']} -> {e['tgt']}  (bal={e['balance']:.2f})"
            )
        lines.append("")

    worst = sorted(rep["edges"], key=lambda e: e["balance"])[:top]
    lines.append(f"Hotspots (lowest balance, top {top}):")
    for e in worst:
        lines.append(
            f"  bal={e['balance']:.2f}  S={e['strength']:.2f}({e['strength_label']})"
            f" D={e['distance']:.2f}({e['distance_label']})"
            f" V={e['volatility']:.2f}({e['volatility_label']})"
            f"  {e['src']} -> {e['tgt']}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="django-coupling")
    ap.add_argument("path", help="package/directory to analyze")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--top", type=int, default=15, help="how many rows to show (default 15)")
    ap.add_argument("--since", default="6 months ago", help="git window for volatility")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.path):
        print(f"error: not a directory: {args.path}", file=sys.stderr)
        return 2

    rep = analyze(args.path, since=args.since)
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        print(_render_text(rep, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
