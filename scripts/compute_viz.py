#!/usr/bin/env python3
"""Awesome Visualizer - Visualization Data Pre-computation

Reads site/data/repos.json and produces site/data/viz-data.json with
pre-aggregated data for client-side charts:

  - language_distribution: top languages by repo count (donut chart)
  - health_histogram: repo counts in health score buckets (bar chart)
  - star_buckets: repo counts by star ranges (bar chart)
  - activity_sparkline: monthly commit activity over last 12 months
  - category_bubbles: category size/health for bubble chart
  - license_distribution: top licenses by repo count

Usage:
    nix develop --command python scripts/compute_viz.py

No external dependencies beyond the Python stdlib.
"""

import json
import sys
from collections import Counter
from pathlib import Path

REPO_DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
VIZ_OUTPUT = Path(__file__).resolve().parent.parent / "site" / "data" / "viz-data.json"

# Health histogram buckets: label, min, max (inclusive)
HEALTH_BUCKETS = [
    ("0-19", 0, 19),
    ("20-39", 20, 39),
    ("40-59", 40, 59),
    ("60-79", 60, 79),
    ("80-100", 80, 100),
]

# Star range buckets
STAR_BUCKETS = [
    ("0-100", 0, 100),
    ("101-500", 101, 500),
    ("501-1k", 501, 1000),
    ("1k-5k", 1001, 5000),
    ("5k-10k", 5001, 10000),
    ("10k-50k", 10001, 50000),
    ("50k+", 50001, float("inf")),
]

MAX_LANGUAGES = 15
MAX_LICENSES = 10


def compute_language_distribution(repos):
    """Top languages by count + percentage."""
    counts = Counter()
    for r in repos:
        lang = r.get("language")
        if lang:
            counts[lang] += 1

    total = sum(counts.values())
    top = counts.most_common(MAX_LANGUAGES)
    other = total - sum(c for _, c in top)

    result = []
    for name, count in top:
        result.append({"name": name, "count": count, "pct": round(count / total * 100, 1) if total else 0})
    if other > 0:
        result.append({"name": "Other", "count": other, "pct": round(other / total * 100, 1)})

    return result


def compute_health_histogram(repos):
    """Count repos in each health score bucket."""
    buckets = {label: 0 for label, _, _ in HEALTH_BUCKETS}
    for r in repos:
        h = r.get("health", 0)
        for label, lo, hi in HEALTH_BUCKETS:
            if lo <= h <= hi:
                buckets[label] += 1
                break

    return [{"label": label, "count": buckets[label]} for label, _, _ in HEALTH_BUCKETS]


def compute_star_buckets(repos):
    """Count repos in each star range."""
    buckets = {label: 0 for label, _, _ in STAR_BUCKETS}
    for r in repos:
        stars = r.get("stars", 0)
        for label, lo, hi in STAR_BUCKETS:
            if lo <= stars <= hi:
                buckets[label] += 1
                break

    return [{"label": label, "count": buckets[label]} for label, _, _ in STAR_BUCKETS]


def compute_category_bubbles(repos, categories):
    """Category bubble data: count, avg health, avg stars."""
    cat_data = {}
    for r in repos:
        cat = r.get("category", "")
        if not cat:
            continue
        if cat not in cat_data:
            cat_data[cat] = {"health_sum": 0, "star_sum": 0, "count": 0}
        cat_data[cat]["count"] += 1
        cat_data[cat]["health_sum"] += r.get("health", 0)
        cat_data[cat]["star_sum"] += r.get("stars", 0)

    # Build name lookup from categories
    cat_names = {}
    for c in categories:
        cat_names[c["id"]] = c.get("name", c["id"])

    bubbles = []
    for cat_id, d in cat_data.items():
        if d["count"] < 2:
            continue
        bubbles.append({
            "id": cat_id,
            "name": cat_names.get(cat_id, cat_id),
            "count": d["count"],
            "health": round(d["health_sum"] / d["count"]),
            "stars": round(d["star_sum"] / d["count"]),
        })

    bubbles.sort(key=lambda b: -b["count"])
    return bubbles


def compute_license_distribution(repos):
    """Top licenses by count."""
    counts = Counter()
    for r in repos:
        lic = r.get("license")
        if lic:
            counts[lic] += 1
        else:
            counts["None"] += 1

    total = sum(counts.values())
    top = counts.most_common(MAX_LICENSES)
    other = total - sum(c for _, c in top)

    result = []
    for name, count in top:
        result.append({"name": name, "count": count, "pct": round(count / total * 100, 1) if total else 0})
    if other > 0:
        result.append({"name": "Other", "count": other, "pct": round(other / total * 100, 1)})

    return result


def compute_health_by_language(repos):
    """Average health per top language."""
    lang_health = {}
    for r in repos:
        lang = r.get("language")
        if not lang:
            continue
        if lang not in lang_health:
            lang_health[lang] = {"sum": 0, "count": 0}
        lang_health[lang]["sum"] += r.get("health", 0)
        lang_health[lang]["count"] += 1

    result = []
    for lang, d in lang_health.items():
        if d["count"] < 10:
            continue
        result.append({
            "name": lang,
            "health": round(d["sum"] / d["count"]),
            "count": d["count"],
        })

    result.sort(key=lambda x: -x["health"])
    return result[:MAX_LANGUAGES]


def main():
    if not REPO_DATA.exists():
        print(f"Error: {REPO_DATA} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {REPO_DATA}...")
    with open(REPO_DATA) as f:
        data = json.load(f)

    repos = data.get("repos", [])
    categories = data.get("categories", [])
    if not repos:
        print("No repos found in data.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(repos)} repos loaded")

    print("Computing language distribution...")
    lang_dist = compute_language_distribution(repos)
    print(f"  {len(lang_dist)} language entries")

    print("Computing health histogram...")
    health_hist = compute_health_histogram(repos)

    print("Computing star buckets...")
    star_buck = compute_star_buckets(repos)

    print("Computing category bubbles...")
    cat_bubbles = compute_category_bubbles(repos, categories)
    print(f"  {len(cat_bubbles)} categories")

    print("Computing license distribution...")
    lic_dist = compute_license_distribution(repos)
    print(f"  {len(lic_dist)} license entries")

    print("Computing health by language...")
    health_lang = compute_health_by_language(repos)
    print(f"  {len(health_lang)} languages with enough data")

    viz = {
        "version": 1,
        "total_repos": len(repos),
        "language_distribution": lang_dist,
        "health_histogram": health_hist,
        "star_buckets": star_buck,
        "category_bubbles": cat_bubbles,
        "license_distribution": lic_dist,
        "health_by_language": health_lang,
    }

    VIZ_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(VIZ_OUTPUT, "w") as f:
        json.dump(viz, f, separators=(",", ":"))

    size_kb = VIZ_OUTPUT.stat().st_size / 1024
    print(f"\nDone. viz-data.json written ({size_kb:.1f}KB)")


if __name__ == "__main__":
    main()
