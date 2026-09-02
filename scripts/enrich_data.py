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
    ["a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is", "it", "of", "on", "or", "the", "this", "to", "was", "were", "will", "with", "that", "not", "but", "can", "all", "your", "more", "about", "up", "its", "out", "do", "so", "than", "them", "been", "could", "into", "some", "which", "would", "there", "their", "what", "when", "who", "how", "she", "he", "we", "they", "my", "our", "his", "her", "most", "also", "may", "over", "only", "very", "just", "where", "should", "now", "each", "make", "like", "way", "these", "two", "many", "then", "did", "get", "use", "made", "after", "new", "used", "using", "such", "no", "any", "other", "repo", "repository", "list", "awesome", "curated", "collection", "resources"]
)

MIN_TERM_LEN = 2
MAX_SUGGESTIONS = 200
MIN_KEYWORDS_PER_DOC = 5
MAX_KEYWORDS_PER_DOC = 15
TOP_TERMS_PER_CATEGORY = 20

# BM25 parameters
BM25_K1 = 1.5
BM25_B = 0.75

# Synonym map: canonical -> list of aliases.
# Both directions are indexed - searching "js" matches "javascript" and vice versa.
SYNONYM_GROUPS = [
    ["javascript", "js"],
    ["typescript", "ts"],
    ["python", "py"],
    ["golang", "go"],
    ["rust", "rs"],
    ["csharp", "c-sharp", "cs", "dotnet"],
    ["cpp", "c-plus-plus", "cplusplus"],
    ["kubernetes", "k8s"],
    ["postgres", "postgresql"],
    ["mongo", "mongodb"],
    ["redis", "key-value"],
    ["react", "reactjs"],
    ["vue", "vuejs"],
    ["angular", "angularjs"],
    ["node", "nodejs"],
    ["deno", "denojs"],
    ["tensorflow", "tf"],
    ["pytorch", "torch"],
    ["machine-learning", "ml"],
    ["deep-learning", "dl"],
    ["artificial-intelligence", "ai"],
    ["natural-language-processing", "nlp"],
    ["computer-vision", "cv"],
    ["devops", "dev-ops"],
    ["ci-cd", "continuous-integration"],
    ["api", "rest-api", "restful"],
    ["graphql", "gql"],
    ["sql", "structured-query-language"],
    ["nosql", "non-relational"],
    ["aws", "amazon-web-services"],
    ["gcp", "google-cloud"],
    ["azure", "microsoft-azure"],
]

# Build bidirectional lookup: term -> set of all synonyms (excluding self)
_SYNONYM_MAP = {}
for _group in SYNONYM_GROUPS:
    for _term in _group:
        _SYNONYM_MAP[_term] = [t for t in _group if t != _term]


def tokenize(text):
    """Split text into normalized lowercase tokens."""
    if not text:
        return []
    text = text.lower()
    tokens = re.findall(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", text)
    return [t for t in tokens if len(t) >= MIN_TERM_LEN and t not in STOP_WORDS]


def bigrams(text):
    """Extract adjacent 2-word phrases from text (post-stopword filtering).

    Bigrams capture meaningful multi-word concepts like "machine-learning",
    "real-time", "deep-learning" that unigrams miss.
    """
    if not text:
        return []
    text = text.lower()
    raw = re.findall(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", text)
    # Filter stop words but keep position proximity
    filtered = [t for t in raw if len(t) >= MIN_TERM_LEN and t not in STOP_WORDS]
    pairs = []
    for i in range(len(filtered) - 1):
        pairs.append(filtered[i] + "_" + filtered[i + 1])
    return pairs


def build_repo_tokens(repo):
    """Extract per-field token lists from a repo record for BM25F."""
    desc = repo.get("description", "")
    topic_text = " ".join(repo.get("topics", []))
    fields = {
        "name": (tokenize(repo.get("name", "")), 3.0),
        "owner": (tokenize(repo.get("owner", "")), 1.5),
        "full_name": (tokenize(repo.get("full_name", "").replace("/", " ")), 2.0),
        "description": (tokenize(desc), 1.0),
        "desc_bigrams": (bigrams(desc), 1.5),
        "topics": (sum((tokenize(t) for t in repo.get("topics", [])), []), 2.5),
        "topic_bigrams": (bigrams(topic_text), 2.0),
        "language": (tokenize(repo.get("language", "")), 2.0),
        "category": (tokenize(repo.get("category", "").replace("-", " ")), 1.0),
        "subcategory": (tokenize(repo.get("subcategory", "")), 1.0),
    }
    return fields


def _bm25f_weighted_tf(fields):
    """Compute BM25F weighted term frequency across multiple fields.

    Instead of naively summing weighted counts, BM25F computes:
        tf_tilde(term) = sum_field(w_field * tf_field(term))
    and returns the combined tf dict plus total doc length.
    """
    combined_tf = {}
    doc_len = 0
    for _field_name, (tokens, weight) in fields.items():
        field_tf = {}
        for t in tokens:
            field_tf[t] = field_tf.get(t, 0) + 1
        for term, count in field_tf.items():
            combined_tf[term] = combined_tf.get(term, 0) + weight * count
        doc_len += len(tokens)
    return combined_tf, doc_len


def compute_keywords(repos):
    """Compute BM25F keywords per repo.

    Returns:
        repo_keywords: list of keyword strings per repo index
        doc_freq: term -> doc frequency counter
    """
    n = len(repos)
    repo_tf = []
    doc_lengths = []
    doc_freq = Counter()

    for repo in repos:
        fields = build_repo_tokens(repo)
        combined_tf, doc_len = _bm25f_weighted_tf(fields)
        repo_tf.append(combined_tf)
        doc_lengths.append(doc_len)
        for term in combined_tf:
            doc_freq[term] += 1

    avgdl = sum(doc_lengths) / n if n > 0 else 1

    # BM25 IDF
    idf = {}
    for term, df in doc_freq.items():
        idf[term] = math.log((n - df + 0.5) / (df + 0.5) + 1)

    repo_keywords = []
    for i, tf in enumerate(repo_tf):
        dl = doc_lengths[i]
        scores = {}
        for term, wtf in tf.items():
            # BM25 scoring with BM25F weighted term frequency
            numerator = wtf * (BM25_K1 + 1)
            denominator = wtf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            scores[term] = idf.get(term, 0) * numerator / denominator
        # Dynamic keyword count based on token richness
        max_kw = min(MAX_KEYWORDS_PER_DOC, max(MIN_KEYWORDS_PER_DOC, dl // 8))
        top = sorted(scores.items(), key=lambda x: -x[1])[:max_kw]
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
        fields = build_repo_tokens(repo)
        combined_tf, _ = _bm25f_weighted_tf(fields)
        for term, weight in combined_tf.items():
            cat_terms[cat][term] += weight

    result = {}
    for cat, counter in cat_terms.items():
        top = counter.most_common(TOP_TERMS_PER_CATEGORY)
        result[cat] = [t for t, _ in top]

    return result


def build_resource_tokens(resource):
    """Extract per-field token lists from a resource record."""
    title = resource.get("title", "")
    desc = resource.get("description", "")
    return {
        "title": (tokenize(title), 3.0),
        "title_bigrams": (bigrams(title), 2.0),
        "description": (tokenize(desc), 1.0),
        "desc_bigrams": (bigrams(desc), 1.5),
        "category": (tokenize(resource.get("category", "").replace("-", " ")), 1.0),
        "subcategory": (tokenize(resource.get("subcategory", "")), 1.0),
    }


def compute_resource_keywords(resources):
    """Compute BM25F keywords per resource."""
    n = len(resources)
    if n == 0:
        return [], Counter()
    resource_tf = []
    doc_lengths = []
    doc_freq = Counter()

    for res in resources:
        fields = build_resource_tokens(res)
        combined_tf, doc_len = _bm25f_weighted_tf(fields)
        resource_tf.append(combined_tf)
        doc_lengths.append(doc_len)
        for term in combined_tf:
            doc_freq[term] += 1

    avgdl = sum(doc_lengths) / n if n > 0 else 1

    idf = {}
    for term, df in doc_freq.items():
        idf[term] = math.log((n - df + 0.5) / (df + 0.5) + 1)

    resource_keywords = []
    for i, tf in enumerate(resource_tf):
        dl = doc_lengths[i]
        scores = {}
        for term, wtf in tf.items():
            numerator = wtf * (BM25_K1 + 1)
            denominator = wtf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            scores[term] = idf.get(term, 0) * numerator / denominator
        max_kw = min(MAX_KEYWORDS_PER_DOC, max(MIN_KEYWORDS_PER_DOC, dl // 8))
        top = sorted(scores.items(), key=lambda x: -x[1])[:max_kw]
        resource_keywords.append([t for t, _ in top])

    return resource_keywords, doc_freq


def main():
    if not REPO_DATA.exists():
        print(f"Error: {REPO_DATA} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {REPO_DATA}...")
    with REPO_DATA.open() as f:
        data = json.load(f)

    repos = data.get("repos", [])
    resources = data.get("resources", [])
    if not repos:
        print("No repos found in data.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(repos)} repos, {len(resources)} resources loaded")

    # Compute BM25F keywords per repo
    print("Computing BM25F keywords...")
    repo_keywords, doc_freq = compute_keywords(repos)
    print(f"  {len(doc_freq)} unique terms analyzed")

    # Inject keywords into repo records (with synonym expansion)
    enriched_count = 0
    for i, repo in enumerate(repos):
        kw = repo_keywords[i]
        if kw:
            # Expand keywords with synonyms so search for "js" matches "javascript"
            expanded = set(kw)
            for term in kw:
                for alias in _SYNONYM_MAP.get(term, []):
                    expanded.add(alias)
            repo["kw"] = " ".join(expanded)
            enriched_count += 1

    print(f"  {enriched_count} repos enriched with keywords")

    # Compute BM25F keywords per resource
    if resources:
        print("Computing resource keywords...")
        res_keywords, res_doc_freq = compute_resource_keywords(resources)
        res_enriched = 0
        for i, res in enumerate(resources):
            kw = res_keywords[i]
            if kw:
                res["kw"] = " ".join(kw)
                res_enriched += 1
        print(f"  {res_enriched} resources enriched with keywords")
        # Merge resource doc_freq into main doc_freq for suggestions
        for term, freq in res_doc_freq.items():
            doc_freq[term] = doc_freq.get(term, 0) + freq

    # Write enriched repos.json back
    with REPO_DATA.open("w") as f:
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
    with META_OUTPUT.open("w") as f:
        json.dump(meta, f, separators=(",", ":"))

    meta_size_kb = META_OUTPUT.stat().st_size / 1024
    print(f"\nDone. search-meta.json written ({meta_size_kb:.1f}KB)")


if __name__ == "__main__":
    main()
