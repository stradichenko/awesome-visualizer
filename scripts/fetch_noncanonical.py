#!/usr/bin/env python3
"""Awesome Visualizer - Non-Canonical Awesome List Discovery

Discovers awesome lists that are NOT in the official sindresorhus/awesome
ecosystem but share similar characteristics:
  - Repo name contains "awesome"
  - README is primarily a curated link list
  - Average health of linked repos > 50

Uses GitHub Search API to find candidates, filters them, crawls their
READMEs, batch-queries linked repos via GraphQL, and appends results
to site/data/repos.json under a "non_canonical_categories" key.

Usage:
    nix develop --command python scripts/fetch_noncanonical.py

Requires GITHUB_TOKEN environment variable.
"""

import base64
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"
REPO_DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
BATCH_SIZE = 40
NINETY_DAYS_AGO = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
REST_DELAY = 2.5  # GitHub Search API has stricter rate limits
GQL_DELAY = 0.5
MAX_RETRIES = 3
RETRY_DELAY = 2
SEARCH_PAGES = 10  # 10 pages x 100 results = 1000 candidates max
MIN_STARS = 50  # Skip very low-quality repos
MIN_LINK_COUNT = 10  # README must have at least this many GitHub links
MIN_HEALTH = 50  # Average health of linked repos must exceed this
AWESOME_BADGE_RE = re.compile(r"awesome\.re/badge", re.IGNORECASE)


def get_token():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return token


def _request(url, token, method="GET", body=None, content_type=None, _retries=0):
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
            return _request(url, token, method, body, content_type, _retries)
        if e.code == 404:
            return None
        if e.code == 422:
            print(f"  Search validation error for {url}", file=sys.stderr)
            return None
        if e.code in (500, 502, 503) and _retries < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** _retries)
            print(f"  HTTP {e.code} - retrying in {delay}s ...", file=sys.stderr)
            time.sleep(delay)
            return _request(url, token, method, body, content_type, _retries + 1)
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except (TimeoutError, OSError) as e:
        if _retries < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** _retries)
            print(f"  Network error: {e} - retrying in {delay}s ...", file=sys.stderr)
            time.sleep(delay)
            return _request(url, token, method, body, content_type, _retries + 1)
        print(f"  Network error for {url}: {e}", file=sys.stderr)
        return None


def github_rest(path, token):
    url = path if path.startswith("http") else f"{GITHUB_API}/{path}"
    return _request(url, token)


def github_graphql(query, token):
    body = json.dumps({"query": query}).encode()
    data = _request(GITHUB_GRAPHQL, token, method="POST", body=body, content_type="application/json")
    if not data:
        return {}
    if "errors" in data:
        for err in data["errors"]:
            print(f"  GraphQL error: {err.get('message', '?')}", file=sys.stderr)
    return data.get("data") or {}


def slugify(text):
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def fetch_repo_readme(full_name, token):
    data = github_rest(f"repos/{full_name}/readme", token)
    if not data or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8")
    except Exception:
        return None


def extract_github_links(text):
    """Extract GitHub repo links from markdown text."""
    links = []
    seen = set()
    for _, repo_path in re.findall(
        r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
        text,
    ):
        clean = repo_path.strip("/").lower()
        if clean.count("/") == 1 and clean not in seen:
            seen.add(clean)
            links.append(repo_path.strip("/"))
    return links


def looks_like_curated_list(readme_text):
    """Check if a README looks like a curated link list.

    Heuristics:
    - Has multiple GitHub links
    - Links account for a meaningful portion of the content
    - Has section headings (## or ###)
    """
    if not readme_text:
        return False, 0

    links = extract_github_links(readme_text)
    link_count = len(links)
    if link_count < MIN_LINK_COUNT:
        return False, link_count

    # Count section headings
    headings = len(re.findall(r"^#{2,4}\s+", readme_text, re.MULTILINE))
    if headings < 2:
        return False, link_count

    # Link density check: at least 1 link per 500 chars of README
    ratio = link_count / max(1, len(readme_text) / 500)
    if ratio < 0.3:
        return False, link_count

    return True, link_count


def parse_list_readme(readme_text, category_name, category_id, source_repo):
    """Extract repos from a list README with subcategory headings."""
    repos = []
    current_sub = "General"
    skip_sections = {"contents", "license", "contributing", "footnotes", "related", "about", "meta"}
    source_lower = source_repo.lower()

    for line in readme_text.split("\n"):
        heading = re.match(r"^#{2,4}\s+(.+)", line)
        if heading:
            text = heading.group(1).strip()
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
            "description": (rd.get("description") or "")[:150],
            "stars": rd["stargazerCount"],
            "forks": rd["forkCount"],
            "open_issues": rd["issues"]["totalCount"],
            "language": (rd.get("primaryLanguage") or {}).get("name", ""),
            "license": (rd.get("licenseInfo") or {}).get("spdxId", ""),
            "last_push": rd.get("pushedAt", ""),
            "is_archived": rd.get("isArchived", False),
            "commits_90d": commits_90d,
            "topics": topics[:5],
            "category": info["category"],
            "subcategory": info.get("subcategory", "General"),
            "subcategory_id": info.get("subcategory_id", "general"),
        }
        rec["health"] = compute_health(rec)
        rec["is_awesome_list"] = False
        rec["is_non_canonical"] = True
        repos.append(rec)

    return repos


def search_awesome_repos(token, exclude_set):
    """Search GitHub for repos with 'awesome' in name, not in canonical set."""
    candidates = []
    seen = set()

    query = "awesome in:name stars:>=" + str(MIN_STARS) + " fork:false"
    encoded = quote(query)

    for page in range(1, SEARCH_PAGES + 1):
        url = f"{GITHUB_API}/search/repositories?q={encoded}&sort=stars&order=desc&per_page=100&page={page}"
        print(f"  Search page {page}/{SEARCH_PAGES}...", end="", flush=True)

        data = github_rest(url, token)
        if not data or "items" not in data:
            print(" no results")
            break

        items = data["items"]
        if not items:
            print(" empty page")
            break

        added = 0
        for item in items:
            full_name = item.get("full_name", "")
            fn_lower = full_name.lower()

            # Skip if already in canonical set
            if fn_lower in exclude_set or fn_lower in seen:
                continue

            # Must have "awesome" in the repo name
            repo_name = full_name.split("/")[-1].lower()
            if "awesome" not in repo_name:
                continue

            seen.add(fn_lower)
            candidates.append({
                "full_name": full_name,
                "name": item.get("name", ""),
                "description": (item.get("description") or "")[:150],
                "stars": item.get("stargazers_count", 0),
            })
            added += 1

        print(f" +{added} candidates")
        time.sleep(REST_DELAY)

        # Stop if fewer than 100 results (last page)
        if len(items) < 100:
            break

    return candidates


def main():
    token = get_token()

    # Load existing canonical data
    if not REPO_DATA.exists():
        print("Error: repos.json not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    with open(REPO_DATA) as f:
        existing = json.load(f)

    # Build exclusion set from canonical repos and categories
    exclude_set = set()
    for r in existing.get("repos", []):
        exclude_set.add(r["full_name"].lower())
    for c in existing.get("categories", []):
        sr = c.get("source_repo", "")
        if sr:
            exclude_set.add(sr.lower())

    print(f"Canonical set: {len(exclude_set)} known repos/lists")

    # Step 1: Search GitHub for awesome-* repos
    print("\nSearching GitHub for non-canonical awesome lists...")
    candidates = search_awesome_repos(token, exclude_set)
    print(f"\n  {len(candidates)} candidate repos found")

    # Step 2: Validate candidates by checking their READMEs
    print("\nValidating candidates (checking READMEs)...")
    validated = []
    for i, cand in enumerate(candidates):
        tag = f"[{i + 1}/{len(candidates)}]"
        fn = cand["full_name"]
        print(f"  {tag} {fn}...", end="", flush=True)

        readme = fetch_repo_readme(fn, token)
        if not readme:
            print(" no README")
            time.sleep(REST_DELAY)
            continue

        # Skip if it has the awesome badge (it should be canonical)
        if AWESOME_BADGE_RE.search(readme):
            print(" has badge (should be canonical)")
            time.sleep(REST_DELAY)
            continue

        is_list, link_count = looks_like_curated_list(readme)
        if not is_list:
            print(f" not a list ({link_count} links)")
            time.sleep(REST_DELAY)
            continue

        print(f" valid list ({link_count} links)", flush=True)
        validated.append({
            "full_name": fn,
            "name": cand["name"],
            "description": cand["description"],
            "stars": cand["stars"],
            "readme": readme,
            "link_count": link_count,
        })
        time.sleep(REST_DELAY)

    print(f"\n  {len(validated)} validated non-canonical lists")

    if not validated:
        print("No non-canonical lists found. Exiting.")
        existing["non_canonical_categories"] = []
        with open(REPO_DATA, "w") as f:
            json.dump(existing, f, separators=(",", ":"))
        return

    # Step 3: Crawl validated lists for project repos
    print("\nCrawling non-canonical lists for repos...")
    all_links = []
    nc_cat_meta = {}

    for v in validated:
        cid = slugify(v["name"])
        cname = v["name"].replace("-", " ").replace("awesome ", "").replace("Awesome ", "").title()
        # Prefix with original name if slugify would collide
        if cid in nc_cat_meta:
            cid = slugify(v["full_name"].replace("/", "-"))

        nc_cat_meta[cid] = {
            "name": cname,
            "source_repo": v["full_name"],
            "description": v["description"],
            "stars": v["stars"],
            "link_count": v["link_count"],
        }

        links = parse_list_readme(v["readme"], cname, cid, v["full_name"])
        print(f"  {v['full_name']}: {len(links)} repos -> {cname}")
        all_links.extend(links)

    # Deduplicate (exclude canonical repos too)
    seen = set(exclude_set)
    unique = []
    for link in all_links:
        key = link["full_name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(link)

    print(f"\n  {len(unique)} unique non-canonical project repos")

    # Step 4: Batch query GraphQL for metrics
    print("\nFetching GitHub metrics for non-canonical repos...")
    nc_repos = []
    total_batches = (len(unique) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        batch = unique[start:start + BATCH_SIZE]
        print(f"  Batch {batch_num + 1}/{total_batches} ({len(batch)} repos)...", flush=True)

        query = build_graphql_query(batch)
        data = github_graphql(query, token)
        repos = process_batch_result(data, batch)
        nc_repos.extend(repos)

        if batch_num < total_batches - 1:
            time.sleep(GQL_DELAY)

    # Step 5: Compute category-level stats and filter by avg health > MIN_HEALTH
    print("\nComputing category statistics...")
    cat_data = {}
    for r in nc_repos:
        c = r["category"]
        if c not in cat_data:
            cat_data[c] = {"repos": [], "health_sum": 0, "langs": {}}
        cat_data[c]["repos"].append(r)
        cat_data[c]["health_sum"] += r.get("health", 0)
        lang = r.get("language", "")
        if lang:
            cat_data[c]["langs"][lang] = cat_data[c]["langs"].get(lang, 0) + 1

    nc_categories = []
    kept_repos = []
    dropped = 0

    for cid, cd in cat_data.items():
        count = len(cd["repos"])
        if count == 0:
            continue
        avg_health = round(cd["health_sum"] / count)
        if avg_health < MIN_HEALTH:
            dropped += 1
            continue

        meta = nc_cat_meta.get(cid, {})
        top_langs = sorted(cd["langs"].items(), key=lambda x: -x[1])[:5]

        # Count subcategories
        sub_ids = set()
        for r in cd["repos"]:
            sub_ids.add(r.get("subcategory_id", "general"))

        nc_categories.append({
            "id": cid,
            "name": meta.get("name", cid.replace("-", " ").title()),
            "count": count,
            "source_repo": meta.get("source_repo", ""),
            "avg_health": avg_health,
            "is_awesome_list": False,
            "is_non_canonical": True,
            "subcategory_count": len(sub_ids),
            "top_languages": [{"name": l, "count": c} for l, c in top_langs],
        })
        kept_repos.extend(cd["repos"])

    nc_categories.sort(key=lambda c: c["name"])
    print(f"  {len(nc_categories)} categories pass health filter (dropped {dropped})")
    print(f"  {len(kept_repos)} repos in qualifying categories")

    # Step 6: Write back to repos.json
    existing["non_canonical_categories"] = nc_categories

    # Add non-canonical repos to the main repos array
    # Mark them so the frontend can distinguish
    existing_repos = existing.get("repos", [])
    # Remove old non-canonical repos first
    existing_repos = [r for r in existing_repos if not r.get("is_non_canonical")]
    existing_repos.extend(sorted(kept_repos, key=lambda r: -r["stars"]))
    existing["repos"] = existing_repos

    # Update meta
    existing["meta"]["total_repos"] = len(existing_repos)

    with open(REPO_DATA, "w") as f:
        json.dump(existing, f, separators=(",", ":"))

    size_mb = REPO_DATA.stat().st_size / 1024 / 1024
    print(f"\nDone. {len(nc_categories)} non-canonical lists, {len(kept_repos)} repos added.")
    print(f"  Total repos in dataset: {len(existing_repos)} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
