#!/usr/bin/env python3
"""Split repos.json into a lightweight index and per-tier chunk files.

Reads the monolithic repos.json (~150MB) and produces:

  index.json          - categories, subcategories, languages, meta (~1.5MB)
  repos-official.json - official-tier repos array
  repos-unofficial.json - unofficial-tier repos array
  repos-noncanonical.json - non-canonical-tier repos array
  resources-official.json - resources belonging to official categories
  resources-unofficial.json - resources belonging to unofficial categories
  resources-noncanonical.json - resources belonging to non-canonical categories

The front-end loads index.json first for an instant overview, then lazy-loads
tier files on demand when the user expands a segment or opens a detail view.

Usage:
    nix develop --command python scripts/split_data.py
"""

import json
import sys
from pathlib import Path

REPO_DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
OUT_DIR = REPO_DATA.parent

TIER_MAP = {
    "official": "official",
    "unofficial": "unofficial",
    "non-canonical": "noncanonical",
}


def main():
    if not REPO_DATA.exists():
        print(f"Error: {REPO_DATA} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {REPO_DATA}...")
    with REPO_DATA.open() as f:
        data = json.load(f)

    # Build category-id to tier lookup
    cat_tier = {}
    for cat in data.get("categories", []):
        cat_tier[cat["id"]] = "official"
    for cat in data.get("unofficial_categories", []):
        cat_tier[cat["id"]] = "unofficial"
    for cat in data.get("non_canonical_categories", []):
        cat_tier[cat["id"]] = "noncanonical"

    # Count resources per category for overview cards
    res_counts = {}
    for res in data.get("resources", []):
        cid = res.get("category", "")
        res_counts[cid] = res_counts.get(cid, 0) + 1

    # Inject resource_count into each category list
    for key in ("categories", "unofficial_categories", "non_canonical_categories"):
        for cat in data.get(key, []):
            cat["resource_count"] = res_counts.get(cat["id"], 0)

    # Partition repos by tier
    repos_by_tier = {"official": [], "unofficial": [], "noncanonical": []}
    for repo in data.get("repos", []):
        tier_raw = repo.get("tier", "official")
        bucket = TIER_MAP.get(tier_raw, "official")
        repos_by_tier[bucket].append(repo)

    # Partition resources by the tier of their parent category.
    # Drop orphaned resources whose category no longer exists.
    res_by_tier = {"official": [], "unofficial": [], "noncanonical": []}
    dropped_resources = 0
    for res in data.get("resources", []):
        cid = res.get("category", "")
        if cid not in cat_tier:
            dropped_resources += 1
            continue
        res_by_tier[cat_tier[cid]].append(res)
    if dropped_resources:
        print(f"  Dropped {dropped_resources} orphaned resources (no matching category)")

    # Build the lightweight index (no repos, no resources)
    meta = data.get("meta", {})
    meta["tier_counts"] = {
        tier: len(repos) for tier, repos in repos_by_tier.items()
    }
    meta["tier_resource_counts"] = {
        tier: len(res) for tier, res in res_by_tier.items()
    }

    index = {
        "meta": meta,
        "categories": data.get("categories", []),
        "unofficial_categories": data.get("unofficial_categories", []),
        "non_canonical_categories": data.get("non_canonical_categories", []),
        "subcategories": data.get("subcategories", []),
        "languages": data.get("languages", []),
    }

    # Write files
    def write_json(name, obj):
        path = OUT_DIR / name
        with path.open("w") as f:
            json.dump(obj, f, separators=(",", ":"))
        size = path.stat().st_size
        if size > 1024 * 1024:
            print(f"  {name}: {size / 1024 / 1024:.1f}MB")
        else:
            print(f"  {name}: {size / 1024:.0f}KB")

    print("Writing split files...")
    write_json("index.json", index)
    for tier, repos in repos_by_tier.items():
        write_json(f"repos-{tier}.json", repos)
    for tier, resources in res_by_tier.items():
        write_json(f"resources-{tier}.json", resources)

    print("\nDone. Front-end will load index.json first, then lazy-load tier files on demand.")


if __name__ == "__main__":
    main()
