#!/usr/bin/env python3
"""
Analyze duplicate review calibration logs.

Usage:
    ~/.pyenv/versions/3.11.9/bin/python scripts/analyze_duplicate_review_calibration.py
    ~/.pyenv/versions/3.11.9/bin/python scripts/analyze_duplicate_review_calibration.py data/duplicate_review_calibration.jsonl
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


def _load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _quantiles(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    if not values:
        return {}

    def pick(q: float) -> float:
        idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
        return values[idx]

    return {
        "min": values[0],
        "p25": pick(0.25),
        "p50": pick(0.50),
        "p75": pick(0.75),
        "max": values[-1],
        "mean": sum(values) / len(values),
    }


def _format_stats(name: str, values: Iterable[float]) -> str:
    vals = [float(v) for v in values]
    if not vals:
        return f"{name}: no data"
    q = _quantiles(vals)
    return (
        f"{name}: n={len(vals)} "
        f"min={q['min']:.4f} p25={q['p25']:.4f} p50={q['p50']:.4f} "
        f"p75={q['p75']:.4f} max={q['max']:.4f} mean={q['mean']:.4f}"
    )


def _safe_values(rows: list[dict], field: str) -> list[float]:
    vals = []
    for row in rows:
        value = row.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            vals.append(float(value))
    return vals


def _metric_values(rows: list[dict], field: str) -> list[float]:
    vals = []
    for row in rows:
        metrics = row.get("metrics") or {}
        value = metrics.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            vals.append(float(value))
    return vals


def _duplicate_hunt_score(row: dict) -> float:
    metrics = row.get("metrics") or {}
    signal = float(row.get("signal", 1.0) or 1.0)
    pixel_ratio = float(metrics.get("pixel_ratio", 0.0) or 0.0)
    filesize_ratio = float(metrics.get("filesize_ratio", 0.0) or 0.0)
    mean_abs_diff = float(metrics.get("mean_abs_diff", 1.0) or 1.0)
    blob_ratio = float(metrics.get("largest_blob_ratio", 1.0) or 1.0)
    return (
        (1.0 - signal) * 0.55
        + pixel_ratio * 0.20
        + filesize_ratio * 0.15
        + (1.0 - mean_abs_diff) * 0.05
        + (1.0 - min(blob_ratio / 0.02, 1.0)) * 0.05
    )


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/duplicate_review_calibration.jsonl")
    if not path.exists():
        print(f"Missing calibration file: {path}")
        return 1

    rows = _load_rows(path)
    if not rows:
        print(f"No rows in: {path}")
        return 1

    print(f"File: {path}")
    print(f"Rows: {len(rows)}")
    print()

    print("Counts")
    print(f"  Outcome: {dict(Counter(row.get('outcome', 'unknown') for row in rows))}")
    print(f"  Manual: {dict(Counter(row.get('manual_class', 'unknown') for row in rows))}")
    print(f"  Suggested: {dict(Counter(row.get('suggested_class', 'unknown') for row in rows))}")
    print()

    by_manual = defaultdict(list)
    for row in rows:
        by_manual[row.get("manual_class", "unknown")].append(row)

    print("Signal By Manual Class")
    for manual_class in ("duplicate", "variation", "other"):
        print(" ", _format_stats(manual_class, _safe_values(by_manual.get(manual_class, []), "signal")))
    print()

    print("Key Metrics By Manual Class")
    for manual_class in ("duplicate", "variation"):
        class_rows = by_manual.get(manual_class, [])
        if not class_rows:
            continue
        print(f"  {manual_class}")
        print("   ", _format_stats("largest_blob_ratio", _metric_values(class_rows, "largest_blob_ratio")))
        print("   ", _format_stats("peak_blob_contrast", _metric_values(class_rows, "peak_blob_contrast")))
        print("   ", _format_stats("pixel_ratio", _metric_values(class_rows, "pixel_ratio")))
        print("   ", _format_stats("filesize_ratio", _metric_values(class_rows, "filesize_ratio")))
        print("   ", _format_stats("metadata_adjustment", _metric_values(class_rows, "metadata_adjustment")))
    print()

    confusion = defaultdict(Counter)
    for row in rows:
        confusion[row.get("manual_class", "unknown")][row.get("suggested_class", "unknown")] += 1

    print("Confusion")
    for manual_class, counts in confusion.items():
        print(f"  {manual_class}: {dict(counts)}")
    print()

    dup_signals = _safe_values(by_manual.get("duplicate", []), "signal")
    var_signals = _safe_values(by_manual.get("variation", []), "signal")
    if dup_signals and var_signals:
        dup_q = _quantiles(dup_signals)
        var_q = _quantiles(var_signals)
        suggested_lower = min(dup_q["p75"], var_q["p25"])
        suggested_upper = max(suggested_lower, var_q["p25"])
        midpoint_gap = var_q["p25"] - dup_q["p75"]
        print("Threshold Hint")
        print(f"  Duplicate p75: {dup_q['p75']:.4f}")
        print(f"  Variation p25: {var_q['p25']:.4f}")
        print(f"  Gap: {midpoint_gap:.4f}")
        print(f"  Candidate lower bound: {suggested_lower:.4f}")
        print(f"  Candidate upper bound: {suggested_upper:.4f}")
    else:
        missing = []
        if not dup_signals:
            missing.append("duplicates")
        if not var_signals:
            missing.append("variations")
        print("Threshold Hint")
        print(f"  Not enough balanced data yet. Missing usable samples for: {', '.join(missing)}.")

    hunt_rows = [row for row in rows if row.get("manual_class") in {"duplicate", "variation"}]
    if hunt_rows:
        ranked = sorted(
            ((row, _duplicate_hunt_score(row)) for row in hunt_rows),
            key=lambda item: item[1],
            reverse=True,
        )
        top_100 = ranked[: min(100, len(ranked))]
        top_250 = ranked[: min(250, len(ranked))]
        top_100_dup = sum(1 for row, _ in top_100 if row.get("manual_class") == "duplicate")
        top_250_dup = sum(1 for row, _ in top_250 if row.get("manual_class") == "duplicate")
        score_values_dup = [score for row, score in ranked if row.get("manual_class") == "duplicate"]
        score_values_var = [score for row, score in ranked if row.get("manual_class") == "variation"]
        print()
        print("Duplicate Hunt Hint")
        print(f"  Top 100 duplicate count: {top_100_dup}/{len(top_100)}")
        print(f"  Top 250 duplicate count: {top_250_dup}/{len(top_250)}")
        print(f"  {_format_stats('hunt_score duplicate', score_values_dup)}")
        print(f"  {_format_stats('hunt_score variation', score_values_var)}")
        if score_values_dup and score_values_var:
            dup_q = _quantiles(score_values_dup)
            var_q = _quantiles(score_values_var)
            print(f"  Candidate hunt cutoff (duplicate median): {dup_q['p50']:.4f}")
            print(f"  Variation p75 for hunt score: {var_q['p75']:.4f}")

    mismatches = [row for row in rows if row.get("outcome") == "mismatches"]
    if mismatches:
        print()
        print("Sample Mismatches")
        for row in mismatches[:10]:
            metrics = row.get("metrics") or {}
            print(
                "  "
                f"manual={row.get('manual_class')} "
                f"suggested={row.get('suggested_class')} "
                f"signal={row.get('signal')} "
                f"blob={metrics.get('largest_blob_ratio')} "
                f"peak={metrics.get('peak_blob_contrast')} "
                f"px={metrics.get('pixel_ratio')} "
                f"file={metrics.get('filesize_ratio')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
