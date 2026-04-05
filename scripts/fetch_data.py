#!/usr/bin/env python3
"""Awesome Visualizer - Data Pipeline

Fetches awesome list metadata and repo metrics from GitHub.
Outputs site/data/repos.json for the static site.

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

CATEGORIES = {
    "Platforms": "platforms",
    "Programming Languages": "programming-languages",
    "Front-End Development": "front-end",
    "Back-End Development": "back-end",
    "Computer Science": "computer-science",
    "Big Data": "big-data",
    "Theory": "theory",
    "Books": "books",
    "Editors": "editors",
    "Gaming": "gaming",
    "Development Environment": "dev-environment",
    "Entertainment": "entertainment",
    "Databases": "databases",
    "Media": "media",
    "Learn": "learn",
    "Security": "security",
    "Content Management Systems": "cms",
    "Hardware": "hardware",
    "Business": "business",
    "Work": "work",
    "Networking": "networking",
    "Decentralized Systems": "decentralized",
    "Health and Social Science": "health-social-science",
    "Events": "events",
    "Testing": "testing",
    "Miscellaneous": "miscellaneous",
}


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


def fetch_master_readme(token):
    """Fetch and decode the README of sindresorhus/awesome."""
    data = github_rest(f"repos/{MASTER_LIST}/readme", token)
    if not data or "content" not in data:
        print("Failed to fetch master README", file=sys.stderr)
        sys.exit(1)
    return base64.b64decode(data["content"]).decode("utf-8")


def parse_awesome_readme(readme_text):
    """Extract GitHub repo links grouped by category from the master README."""
    repos = []
    current_category = "miscellaneous"

    for line in readme_text.split("\n"):
        header = re.match(r"^##\s+(.+)", line)
        if header:
            section = header.group(1).strip()
            if section in CATEGORIES:
                current_category = CATEGORIES[section]
            continue

        # Match [Text](https://github.com/owner/repo...)
        for name, repo_path in re.findall(
            r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
            line,
        ):
            clean = repo_path.strip("/")
            if clean.count("/") == 1:
                repos.append({
                    "full_name": clean,
                    "link_name": name,
                    "category": current_category,
                })

    # Deduplicate, keep first occurrence
    seen = set()
    unique = []
    for r in repos:
        key = r["full_name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


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

    # Stars (0-25)
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

    # Recent commits (0-25)
    c90 = rec.get("commits_90d", 0)
    if c90 >= 50:
        score += 25
    elif c90 >= 20:
        score += 20
    elif c90 >= 5:
        score += 15
    elif c90 >= 1:
        score += 8

    # Freshness (0-25)
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

    # Community signals (0-25)
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

        # Commits in 90 days
        commits_90d = 0
        ref = rd.get("defaultBranchRef")
        if ref and ref.get("target"):
            hist = ref["target"].get("history")
            if hist:
                commits_90d = hist.get("totalCount", 0)

        # Topics
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
        }
        rec["health"] = compute_health(rec)
        repos.append(rec)

    return repos


def main():
    token = get_token()

    print(f"Fetching master README from {MASTER_LIST}...")
    readme = fetch_master_readme(token)

    print("Parsing repository links...")
    repo_links = parse_awesome_readme(readme)
    print(f"  Found {len(repo_links)} unique repositories")

    all_repos = []
    total_batches = (len(repo_links) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        batch = repo_links[start : start + BATCH_SIZE]
        print(f"  Querying batch {batch_num + 1}/{total_batches} ({len(batch)} repos)...")

        query = build_graphql_query(batch)
        data = github_graphql(query, token)
        repos = process_batch_result(data, batch)
        all_repos.extend(repos)

        if batch_num < total_batches - 1:
            time.sleep(0.5)

    # Build category summary
    cat_counts = {}
    for r in all_repos:
        c = r["category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1

    categories = []
    for cat_id, count in sorted(cat_counts.items()):
        display = next(
            (k for k, v in CATEGORIES.items() if v == cat_id),
            cat_id.replace("-", " ").title(),
        )
        categories.append({"id": cat_id, "name": display, "count": count})
    categories.sort(key=lambda c: c["name"])

    # Build language summary
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
        "languages": languages,
        "repos": sorted(all_repos, key=lambda r: -r["stars"]),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(all_repos)} repos written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
