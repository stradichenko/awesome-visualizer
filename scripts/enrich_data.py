#!/usr/bin/env python3
"""Awesome Visualizer - Search Enrichment Pipeline

Enriches site/data/repos.json in-place with pre-computed keywords per repo,
and produces a lightweight site/data/search-meta.json with:
  - Autocomplete suggestions (popular terms)
  - Per-category keyword tags

The enriched keywords are injected as a `kw` field on each repo so the
existing client-side string search automatically picks them up.

Usage:
    nix develop --command python scripts/enrich_data.py

No external dependencies beyond the Python stdlib.
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO_DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
META_OUTPUT = Path(__file__).resolve().parent.parent / "site" / "data" / "search-meta.json"

STOP_WORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or the this to "
    "was were will with that not but can all your more about up its out do so "
    "than them been could into some which would there their what when who how "
    "she he we they my our his her most also may over only very just where "
    "should now each make like way these two many then did get use made after "
    "new used using such no any other".split()
)

MIN_TERM_LEN = 2
MAX_SUGGESTIONS = 200
MAX_KEYWORDS_PER_REPO = 10
TOP_TERMS_PER_CATEGORY = 20


def tokenize(text):
    """Split text into normalized lowercase tokens."""
    if not text:
        return []
    text = text.lower()
    tokens = re.findall(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", text)
    return [t for t in tokens if len(t) >= MIN_TERM_LEN and t not in STOP_WORDS]


def build_repo_tokens(repo):
    """Extract weighted tokens from a repo record."""
    weighted = []
    weighted.extend((t, 3.0) for t in tokenize(repo.get("name", "")))
    weighted.extend((t, 1.5) for t in tokenize(repo.get("owner", "")))
    weighted.extend((t, 2.0) for t in tokenize(repo.get("full_name", "").replace("/", " ")))
    weighted.extend((t, 1.0) for t in tokenize(repo.get("description", "")))
    for topic in repo.get("topics", []):
        weighted.extend((t, 2.5) for t in tokenize(topic))
    lang = repo.get("language", "")
    if lang:
        weighted.extend((t, 2.0) for t in tokenize(lang))
    weighted.extend((t, 1.0) for t in tokenize(repo.get("category", "").replace("-", " ")))
    weighted.extend((t, 1.0) for t in tokenize(repo.get("subcategory", "")))
    return weighted


def compute_keywords(repos):
    """Compute TF-IDF keywords per repo.

    Returns:
        repo_keywords: list of keyword strings per repo index
        doc_freq: term -> doc frequency counter
    """
    n = len(repos)
    repo_tf = []
    doc_freq = Counter()

    for repo in repos:
        weighted = build_repo_tokens(repo)
        tf = {}
        for term, weight in weighted:
            tf[term] = tf.get(term, 0) + weight
        repo_tf.append(tf)
        for term in tf:
            doc_freq[term] += 1

    idf = {}
    for term, df in doc_freq.items():
        idf[term] = math.log((n + 1) / (df + 1)) + 1

    repo_keywords = []
    for tf in repo_tf:
        scores = {}
        for term, raw_tf in tf.items():
            scores[term] = raw_tf * idf.get(term, 1.0)
        top = sorted(scores.items(), key=lambda x: -x[1])[:MAX_KEYWORDS_PER_REPO]
        repo_keywords.append([t for t, _ in top])

    return repo_keywords, doc_freq


def build_suggestions(doc_freq, repo_count):
    """Build autocomplete suggestions from popular terms."""
    suggestions = []
    threshold_high = repo_count * 0.5
    threshold_low = max(3, repo_count // 500)

    for term, freq in doc_freq.most_common(MAX_SUGGESTIONS * 3):
        if freq > threshold_high or freq < threshold_low:
            continue
        if len(term) < 3:
            continue
        suggestions.append({"t": term, "c": freq})
        if len(suggestions) >= MAX_SUGGESTIONS:
            break

    return suggestions


def build_category_keywords(repos):
    """Extract top keywords per category."""
    cat_terms = {}
    for repo in repos:
        cat = repo.get("category", "")
        if not cat:
            continue
        if cat not in cat_terms:
            cat_terms[cat] = Counter()
        for term, weight in build_repo_tokens(repo):
            cat_terms[cat][term] += weight

    result = {}
    for cat, counter in cat_terms.items():
        top = counter.most_common(TOP_TERMS_PER_CATEGORY)
        result[cat] = [t for t, _ in top]

    return result


def main():
    if not REPO_DATA.exists():
        print(f"Error: {REPO_DATA} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {REPO_DATA}...")
    with open(REPO_DATA) as f:
        data = json.load(f)

    repos = data.get("repos", [])
    if not repos:
        print("No repos found in data.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(repos)} repos loaded")

    # Compute TF-IDF keywords per repo
    print("Computing TF-IDF keywords...")
    repo_keywords, doc_freq = compute_keywords(repos)
    print(f"  {len(doc_freq)} unique terms analyzed")

    # Inject keywords into repo records
    enriched_count = 0
    for i, repo in enumerate(repos):
        kw = repo_keywords[i]
        if kw:
            repo["kw"] = " ".join(kw)
            enriched_count += 1

    print(f"  {enriched_count} repos enriched with keywords")

    # Write enriched repos.json back
    with open(REPO_DATA, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    repo_size_mb = REPO_DATA.stat().st_size / 1024 / 1024
    print(f"  repos.json updated ({repo_size_mb:.1f}MB)")

    # Build lightweight search metadata
    print("Building autocomplete suggestions...")
    suggestions = build_suggestions(doc_freq, len(repos))
    print(f"  {len(suggestions)} suggestions")

    print("Building category keywords...")
    cat_keywords = build_category_keywords(repos)
    print(f"  {len(cat_keywords)} categories")

    meta = {
        "version": 1,
        "suggestions": suggestions,
        "category_keywords": cat_keywords,
    }

    META_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(META_OUTPUT, "w") as f:
        json.dump(meta, f, separators=(",", ":"))

    meta_size_kb = META_OUTPUT.stat().st_size / 1024
    print(f"\nDone. search-meta.json written ({meta_size_kb:.1f}KB)")


if __name__ == "__main__":
    main()
