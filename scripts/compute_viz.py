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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import HEALTH_BUCKETS, STAR_BUCKETS

REPO_DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
VIZ_OUTPUT = Path(__file__).resolve().parent.parent / "site" / "data" / "viz-data.json"

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


def compute_resource_counts(resources, categories):
    """Resource count per category for bar chart."""
    cat_counts = {}
    for res in resources:
        cat = res.get("category", "")
        if cat:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    cat_names = {}
    for c in categories:
        cat_names[c["id"]] = c.get("name", c["id"])

    result = []
    for cat_id, count in cat_counts.items():
        result.append({
            "label": cat_names.get(cat_id, cat_id),
            "count": count,
        })

    result.sort(key=lambda x: -x["count"])
    return result[:20]


def compute_creation_year_histogram(repos):
    """Count repos by creation year (maturity timeline)."""
    year_counts = Counter()
    for r in repos:
        created = r.get("last_push", "")  # fallback; createdAt not always present
        # Prefer createdAt if available
        ca = r.get("createdAt", r.get("created_at", ""))
        if ca:
            created = ca
        if created and len(created) >= 4:
            try:
                year = int(created[:4])
                if 2005 <= year <= 2030:
                    year_counts[year] += 1
            except ValueError:
                pass

    result = []
    if year_counts:
        for year in range(min(year_counts), max(year_counts) + 1):
            result.append({"label": str(year), "count": year_counts.get(year, 0)})
    return result


def compute_activity_distribution(repos):
    """Count repos by commits_90d ranges."""
    buckets = [
        ("0", 0, 0),
        ("1-5", 1, 5),
        ("6-20", 6, 20),
        ("21-50", 21, 50),
        ("51-100", 51, 100),
        ("100+", 101, float("inf")),
    ]
    counts = {label: 0 for label, _, _ in buckets}
    for r in repos:
        c90 = r.get("commits_90d", 0)
        for label, lo, hi in buckets:
            if lo <= c90 <= hi:
                counts[label] += 1
                break
    return [{"label": label, "count": counts[label]} for label, _, _ in buckets]


def compute_fork_star_ratio(repos):
    """Fork-to-star ratio distribution (collaboration signal)."""
    buckets = [
        ("< 1%", 0, 0.01),
        ("1-5%", 0.01, 0.05),
        ("5-10%", 0.05, 0.10),
        ("10-25%", 0.10, 0.25),
        ("25-50%", 0.25, 0.50),
        ("> 50%", 0.50, float("inf")),
    ]
    counts = {label: 0 for label, _, _ in buckets}
    for r in repos:
        stars = r.get("stars", 0)
        forks = r.get("forks", 0)
        ratio = forks / stars if stars > 0 else 0
        for label, lo, hi in buckets:
            if lo <= ratio < hi:
                counts[label] += 1
                break
    return [{"label": label, "count": counts[label]} for label, _, _ in buckets]


def compute_percentile_thresholds(repos):
    """Compute percentile thresholds for key metrics.

    Returns a dict of metric -> list of {pct, value} entries.
    Frontend can use this to show "top X% by stars" badges.
    """
    metrics = {
        "stars": [],
        "health": [],
        "commits_90d": [],
        "forks": [],
    }
    for r in repos:
        for key in metrics:
            metrics[key].append(r.get(key, 0))

    percentiles = [50, 75, 90, 95, 99]
    result = {}
    for key, values in metrics.items():
        values.sort()
        n = len(values)
        if n == 0:
            result[key] = []
            continue
        thresholds = []
        for p in percentiles:
            idx = min(int(n * p / 100), n - 1)
            thresholds.append({"pct": p, "value": values[idx]})
        result[key] = thresholds
    return result


def compute_topic_cooccurrence(repos):
    """Compute which topics frequently appear together.

    Returns top topic pairs by co-occurrence count.
    """
    pair_counts = Counter()
    for r in repos:
        topics = sorted(set(r.get("topics", [])))
        for i in range(len(topics)):
            for j in range(i + 1, len(topics)):
                pair_counts[(topics[i], topics[j])] += 1

    result = []
    for (t1, t2), count in pair_counts.most_common(50):
        if count < 3:
            break
        result.append({"topics": [t1, t2], "count": count})
    return result


def main():
    if not REPO_DATA.exists():
        print(f"Error: {REPO_DATA} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {REPO_DATA}...")
    with REPO_DATA.open() as f:
        data = json.load(f)

    repos = data.get("repos", [])
    categories = data.get("categories", [])
    resources = data.get("resources", [])
    if not repos:
        print("No repos found in data.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(repos)} repos, {len(resources)} resources loaded")

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

    res_by_cat = []
    if resources:
        print("Computing resource counts by category...")
        res_by_cat = compute_resource_counts(resources, categories)
        print(f"  {len(res_by_cat)} categories with resources")

    print("Computing creation year histogram...")
    creation_hist = compute_creation_year_histogram(repos)
    print(f"  {len(creation_hist)} year buckets")

    print("Computing activity distribution...")
    activity_dist = compute_activity_distribution(repos)

    print("Computing fork/star ratio...")
    fork_star = compute_fork_star_ratio(repos)

    print("Computing percentile thresholds...")
    percentiles = compute_percentile_thresholds(repos)

    print("Computing topic co-occurrence...")
    topic_cooc = compute_topic_cooccurrence(repos)
    print(f"  {len(topic_cooc)} topic pairs")

    viz = {
        "version": 3,
        "total_repos": len(repos),
        "total_resources": len(resources),
        "language_distribution": lang_dist,
        "health_histogram": health_hist,
        "star_buckets": star_buck,
        "category_bubbles": cat_bubbles,
        "license_distribution": lic_dist,
        "health_by_language": health_lang,
        "resource_counts": res_by_cat,
        "creation_year_histogram": creation_hist,
        "activity_distribution": activity_dist,
        "fork_star_ratio": fork_star,
        "percentile_thresholds": percentiles,
        "topic_cooccurrence": topic_cooc,
        "bucket_definitions": {
            "health": [{"label": label, "min": lo, "max": hi} for label, lo, hi in HEALTH_BUCKETS],
            "stars": [{"label": label, "min": lo, "max": hi if hi != float("inf") else None} for label, lo, hi in STAR_BUCKETS],
        },
    }

    VIZ_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with VIZ_OUTPUT.open("w") as f:
        json.dump(viz, f, separators=(",", ":"))

    size_kb = VIZ_OUTPUT.stat().st_size / 1024
    print(f"\nDone. viz-data.json written ({size_kb:.1f}KB)")


if __name__ == "__main__":
    main()
