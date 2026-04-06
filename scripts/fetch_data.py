#!/usr/bin/env python3
"""Awesome Visualizer - Data Pipeline (Deep Crawl)

Two-level crawl:
1. Fetch sindresorhus/awesome README -> discover awesome sub-list repos
2. For each sub-list, fetch its README -> discover individual project repos
3. Batch-query GitHub GraphQL API for metrics on all discovered repos
4. Write site/data/repos.json

Usage:
    nix develop --command python scripts/fetch_data.py

Requires GITHUB_TOKEN environment variable.
"""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

GITHUB_GRAPHQL = "https://api.github.com/graphql"
GITHUB_API = "https://api.github.com"
MASTER_LIST = "sindresorhus/awesome"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
BATCH_SIZE = 40
NINETY_DAYS_AGO = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
MAX_SUBLISTS = 500
REST_DELAY = 0.3
GQL_DELAY = 0.5


def get_token():
    """Read GITHUB_TOKEN from environment."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        print("Set it with: export GITHUB_TOKEN=ghp_...", file=sys.stderr)
        sys.exit(1)
    return token


def _request(url, token, method="GET", body=None, content_type=None):
    """Make an authenticated HTTP request to GitHub."""
    req = Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "awesome-visualizer/1.0")
    if content_type:
        req.add_header("Content-Type", content_type)

    try:
        resp = urlopen(req, body, timeout=30)
        return json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 403:
            reset = int(e.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset - int(time.time()), 30)
            print(f"  Rate limited. Waiting {wait}s ...", file=sys.stderr)
            time.sleep(wait)
            return _request(url, token, method, body, content_type)
        if e.code == 404:
            return None
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None


def github_rest(path, token):
    """GET from GitHub REST API."""
    url = path if path.startswith("http") else f"{GITHUB_API}/{path}"
    return _request(url, token)


def github_graphql(query, token):
    """POST a GraphQL query to GitHub."""
    body = json.dumps({"query": query}).encode()
    data = _request(GITHUB_GRAPHQL, token, method="POST", body=body, content_type="application/json")
    if not data:
        return {}
    if "errors" in data:
        for err in data["errors"]:
            msg = err.get("message", "unknown error")
            print(f"  GraphQL error: {msg}", file=sys.stderr)
    return data.get("data") or {}


def slugify(text):
    """Convert display text to a URL-friendly slug."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def fetch_repo_readme(full_name, token):
    """Fetch and decode a repository's README."""
    data = github_rest(f"repos/{full_name}/readme", token)
    if not data or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8")
    except Exception:
        return None


def extract_github_repo_links(text):
    """Extract [name](github.com/owner/repo) links from markdown."""
    links = []
    for name, repo_path in re.findall(
        r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
        text,
    ):
        clean = repo_path.strip("/")
        if clean.count("/") == 1:
            links.append({"full_name": clean, "link_name": name})
    return links


def parse_master_readme(readme_text):
    """Parse sindresorhus/awesome README to find sub-list repos with section info."""
    sublists = []
    current_section = "Miscellaneous"
    skip_sections = {"contents", "related", "license", "about", "meta"}

    for line in readme_text.split("\n"):
        header = re.match(r"^##\s+(.+)", line)
        if header:
            section = header.group(1).strip()
            if section.lower() not in skip_sections:
                current_section = section
            continue

        for name, repo_path in re.findall(
            r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
            line,
        ):
            clean = repo_path.strip("/")
            if clean.count("/") == 1:
                sublists.append({
                    "full_name": clean,
                    "link_name": name,
                    "section": current_section,
                    "category_name": name,
                    "category_id": slugify(name),
                })

    seen = set()
    unique = []
    for sl in sublists:
        key = sl["full_name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(sl)

    return unique[:MAX_SUBLISTS]


def parse_sublist_readme(readme_text, category_name, category_id, source_repo):
    """Extract individual project repos from a sub-list's README with subcategory headings."""
    repos = []
    current_sub = "General"
    skip_sections = {"contents", "license", "contributing", "footnotes", "related", "about", "meta"}
    source_lower = source_repo.lower()

    for line in readme_text.split("\n"):
        # Detect ##, ###, or #### section headings as subcategories
        heading = re.match(r"^#{2,4}\s+(.+)", line)
        if heading:
            text = heading.group(1).strip()
            # Strip trailing anchors and markdown links
            text = re.sub(r"\s*<.*$", "", text)
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
            text = text.strip(" #")
            if text and text.lower() not in skip_sections:
                current_sub = text
            continue

        for name, repo_path in re.findall(
            r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
            line,
        ):
            clean = repo_path.strip("/")
            if clean.count("/") == 1 and clean.lower() != source_lower:
                repos.append({
                    "full_name": clean,
                    "link_name": name,
                    "category": category_id,
                    "category_name": category_name,
                    "subcategory": current_sub,
                    "subcategory_id": slugify(current_sub),
                })

    return repos


def build_graphql_query(batch):
    """Build a batched GraphQL query for multiple repositories."""
    parts = []
    for i, info in enumerate(batch):
        owner, name = info["full_name"].split("/", 1)
        alias = f"r{i}"
        parts.append(f"""
    {alias}: repository(owner: "{owner}", name: "{name}") {{
      nameWithOwner
      description
      url
      stargazerCount
      forkCount
      isArchived
      issues(states: OPEN) {{ totalCount }}
      pullRequests(states: OPEN) {{ totalCount }}
      primaryLanguage {{ name }}
      licenseInfo {{ spdxId }}
      pushedAt
      createdAt
      updatedAt
      repositoryTopics(first: 10) {{
        nodes {{ topic {{ name }} }}
      }}
      defaultBranchRef {{
        target {{
          ... on Commit {{
            history(since: "{NINETY_DAYS_AGO}") {{
              totalCount
            }}
          }}
        }}
      }}
    }}""")

    return "{" + "".join(parts) + "\n}"


def compute_health(rec):
    """Compute a 0-100 health score from repo metrics."""
    score = 0

    stars = rec.get("stars", 0)
    if stars >= 10000:
        score += 25
    elif stars >= 1000:
        score += 20
    elif stars >= 100:
        score += 15
    elif stars >= 10:
        score += 8
    else:
        score += 2

    c90 = rec.get("commits_90d", 0)
    if c90 >= 50:
        score += 25
    elif c90 >= 20:
        score += 20
    elif c90 >= 5:
        score += 15
    elif c90 >= 1:
        score += 8

    push = rec.get("last_push", "")
    if push:
        try:
            dt = datetime.fromisoformat(push.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - dt).days
            if days <= 30:
                score += 25
            elif days <= 90:
                score += 20
            elif days <= 180:
                score += 15
            elif days <= 365:
                score += 8
            else:
                score += 2
        except (ValueError, TypeError):
            pass

    if rec.get("license"):
        score += 8
    if rec.get("description"):
        score += 7
    if not rec.get("is_archived", False):
        score += 10

    return min(score, 100)


def process_batch_result(data, batch_info):
    """Convert GraphQL response data into repo records."""
    repos = []
    for i, info in enumerate(batch_info):
        alias = f"r{i}"
        rd = data.get(alias)
        if not rd:
            continue

        commits_90d = 0
        ref = rd.get("defaultBranchRef")
        if ref and ref.get("target"):
            hist = ref["target"].get("history")
            if hist:
                commits_90d = hist.get("totalCount", 0)

        topics = []
        for node in (rd.get("repositoryTopics") or {}).get("nodes", []):
            topics.append(node["topic"]["name"])

        nwo = rd["nameWithOwner"]
        rec = {
            "full_name": nwo,
            "name": nwo.split("/")[1],
            "owner": nwo.split("/")[0],
            "url": rd["url"],
            "description": rd.get("description") or "",
            "stars": rd["stargazerCount"],
            "forks": rd["forkCount"],
            "open_issues": rd["issues"]["totalCount"],
            "open_prs": rd["pullRequests"]["totalCount"],
            "language": (rd.get("primaryLanguage") or {}).get("name", ""),
            "license": (rd.get("licenseInfo") or {}).get("spdxId", ""),
            "created_at": rd.get("createdAt", ""),
            "last_push": rd.get("pushedAt", ""),
            "is_archived": rd.get("isArchived", False),
            "commits_90d": commits_90d,
            "topics": topics,
            "category": info["category"],
            "subcategory": info.get("subcategory", "General"),
            "subcategory_id": info.get("subcategory_id", "general"),
        }
        rec["health"] = compute_health(rec)
        repos.append(rec)

    return repos


def main():
    token = get_token()

    # Step 1: Fetch master README
    print(f"Fetching master README from {MASTER_LIST}...")
    readme = fetch_repo_readme(MASTER_LIST, token)
    if not readme:
        print("Failed to fetch master README", file=sys.stderr)
        sys.exit(1)

    # Step 2: Parse master README for sub-lists
    print("Parsing sub-list links...")
    sublists = parse_master_readme(readme)
    print(f"  Found {len(sublists)} sub-lists")

    # Step 3: Crawl each sub-list for project repos
    print("\nCrawling sub-lists for project repos...")
    all_links = []
    cat_meta = {}  # category_id -> {name, source_repo, url}
    for i, sl in enumerate(sublists):
        tag = f"[{i + 1}/{len(sublists)}]"
        cid = sl["category_id"]
        cat_meta[cid] = {
            "name": sl["category_name"],
            "source_repo": sl["full_name"],
            "url": f"https://github.com/{sl['full_name']}",
        }
        print(f"  {tag} {sl['full_name']} ({sl['category_name']})...", end="", flush=True)

        subreadme = fetch_repo_readme(sl["full_name"], token)
        if not subreadme:
            print(" SKIP")
            continue

        links = parse_sublist_readme(subreadme, sl["category_name"], cid, sl["full_name"])
        print(f" {len(links)} repos")
        all_links.extend(links)

        if i < len(sublists) - 1:
            time.sleep(REST_DELAY)

    # Step 4: Deduplicate (first-seen category wins)
    seen = set()
    unique = []
    for link in all_links:
        key = link["full_name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(link)

    print(f"\n  {len(unique)} unique project repos after deduplication")

    # Step 5: Batch query GraphQL for metrics
    print("\nFetching GitHub metrics...")
    all_repos = []
    total_batches = (len(unique) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        batch = unique[start : start + BATCH_SIZE]
        print(f"  Batch {batch_num + 1}/{total_batches} ({len(batch)} repos)...", flush=True)

        query = build_graphql_query(batch)
        data = github_graphql(query, token)
        repos = process_batch_result(data, batch)
        all_repos.extend(repos)

        if batch_num < total_batches - 1:
            time.sleep(GQL_DELAY)

    # Step 6: Build category, subcategory, and language summaries
    cat_counts = {}
    cat_health = {}  # cid -> [health scores]
    cat_langs = {}   # cid -> {lang: count}
    cat_subcats = {} # cid -> set of subcategory_ids
    for r in all_repos:
        c = r["category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1
        cat_health.setdefault(c, []).append(r.get("health", 0))
        lang = r.get("language", "")
        if lang:
            cat_langs.setdefault(c, {}).setdefault(lang, 0)
            cat_langs[c][lang] += 1
        sid = r.get("subcategory_id", "general")
        cat_subcats.setdefault(c, set()).add(sid)

    categories = []
    for cid, count in sorted(cat_counts.items()):
        meta = cat_meta.get(cid, {})
        name = meta.get("name", cid.replace("-", " ").title())
        health_list = cat_health.get(cid, [])
        avg_health = round(sum(health_list) / len(health_list)) if health_list else 0
        top_langs = sorted(
            cat_langs.get(cid, {}).items(), key=lambda x: -x[1]
        )[:5]
        categories.append({
            "id": cid,
            "name": name,
            "count": count,
            "source_repo": meta.get("source_repo", ""),
            "url": meta.get("url", ""),
            "avg_health": avg_health,
            "subcategory_count": len(cat_subcats.get(cid, set())),
            "top_languages": [{"name": l, "count": c} for l, c in top_langs],
        })
    categories.sort(key=lambda c: c["name"])

    # Build subcategory summary grouped by category
    sub_counts = {}
    for r in all_repos:
        key = (r["category"], r.get("subcategory_id", "general"))
        if key not in sub_counts:
            sub_counts[key] = {
                "id": r.get("subcategory_id", "general"),
                "name": r.get("subcategory", "General"),
                "category": r["category"],
                "count": 0,
            }
        sub_counts[key]["count"] += 1

    subcategories = sorted(sub_counts.values(), key=lambda s: (s["category"], s["name"]))

    lang_counts = {}
    for r in all_repos:
        lang = r.get("language", "")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    languages = [
        {"name": k, "count": v}
        for k, v in sorted(lang_counts.items(), key=lambda x: -x[1])
    ]

    output = {
        "meta": {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_repos": len(all_repos),
            "source": f"https://github.com/{MASTER_LIST}",
        },
        "categories": categories,
        "subcategories": subcategories,
        "languages": languages,
        "repos": sorted(all_repos, key=lambda r: -r["stars"]),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(all_repos)} repos written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
