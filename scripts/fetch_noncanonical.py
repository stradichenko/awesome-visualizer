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
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (
    BATCH_RETRIES,
    BATCH_SIZE,
    GQL_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
    compute_health,
)

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"
REPO_DATA = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
CHECKPOINT_FILE = Path(__file__).resolve().parent.parent / "site" / "data" / ".nc_checkpoint.json"
NINETY_DAYS_AGO = (datetime.now(UTC) - timedelta(days=90)).isoformat()
SEARCH_DELAY = 2.5  # GitHub Search API: 30 req/min
REST_DELAY = 0.5   # Core API: 5000 req/hr
SEARCH_PAGES = 10   # 10 pages x 100 results = 1000 candidates max
MIN_STARS = 50      # Skip very low-quality repos
MIN_LINK_COUNT = 10 # README must have at least this many GitHub links
MIN_HEALTH = 50     # Average health of linked repos must exceed this
VALIDATION_WORKERS = 3  # Parallel README fetches during validation
GQL_WORKERS = 2
AWESOME_BADGE_RE = re.compile(r"awesome\.re/badge", re.IGNORECASE)

# Noise filters for resource link extraction
NOISE_DOMAINS_RE = re.compile(
    r"img\.shields\.io|awesome\.re|travis-ci\.|circleci\.com|"
    r"badge\.fury\.io|coveralls\.io|codecov\.io|"
    r"patreon\.com|buymeacoffee\.com|opencollective\.com|paypal\.com|"
    r"twitter\.com|x\.com|linkedin\.com/in|facebook\.com|"
    r"npmjs\.com/package|pypi\.org/project|crates\.io/crates|"
    r"scholar\.google\.",
    re.IGNORECASE,
)
NOISE_PATHS_RE = re.compile(
    r"\.(png|jpg|jpeg|gif|svg|ico)(\?|$)|"
    r"github\.com/[^/]+/[^/]+/(issues|pulls|wiki|blob|tree|actions|releases|commit|compare)",
    re.IGNORECASE,
)
# GitHub paths that look like owner/repo but aren't repositories
NOT_REPO_PREFIXES = frozenset({
    "sponsors", "orgs", "settings", "features", "topics",
    "collections", "marketplace", "apps", "about", "enterprise",
    "pricing", "security", "customer-stories", "readme",
})
GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/?$",
    re.IGNORECASE,
)
LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
RESOURCE_DESC_RE = re.compile(r"^\s*[-*]\s+\[[^\]]+\]\([^)]+\)\s*[-:]?\s*(.*)")


def save_checkpoint(stage, data):
    """Save intermediate progress so the script can resume after a crash."""
    payload = {"stage": stage, "data": data}
    tmp = str(CHECKPOINT_FILE) + ".tmp"
    with Path(tmp).open("w") as f:
        json.dump(payload, f, separators=(",", ":"))
    Path(tmp).replace(CHECKPOINT_FILE)
    print(f"  [checkpoint] Saved at stage '{stage}'")


def load_checkpoint():
    """Load checkpoint if it exists. Returns (stage, data) or (None, None)."""
    if CHECKPOINT_FILE.exists():
        with CHECKPOINT_FILE.open() as f:
            cp = json.load(f)
        return cp.get("stage"), cp.get("data")
    return None, None


def clear_checkpoint():
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


def get_token():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        import subprocess
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        token = result.stdout.strip()
    if not token:
        print("Error: GITHUB_TOKEN is not set and `gh auth token` returned nothing.", file=sys.stderr)
        print("Run `gh auth login` or set GITHUB_TOKEN.", file=sys.stderr)
        sys.exit(1)
    return token


def _request(url, token, method="GET", body=None, content_type=None, _retries=0, _rl_retries=0):
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
            if _rl_retries >= 3:
                print(f"  Rate limited 3 times for {url} - giving up", file=sys.stderr)
                return None
            reset = int(e.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset - int(time.time()), 30)
            print(f"  Rate limited. Waiting {wait}s ...", file=sys.stderr)
            time.sleep(wait)
            return _request(url, token, method, body, content_type, _retries, _rl_retries + 1)
        if e.code == 404:
            return None
        if e.code == 422:
            print(f"  Search validation error for {url}", file=sys.stderr)
            return None
        if e.code in (500, 502, 503, 504) and _retries < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** _retries) + random.uniform(0, RETRY_DELAY)
            print(f"  HTTP {e.code} - retrying in {delay:.0f}s ...", file=sys.stderr)
            time.sleep(delay)
            return _request(url, token, method, body, content_type, _retries + 1)
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except (TimeoutError, OSError, HTTPException) as e:
        if _retries < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** _retries) + random.uniform(0, RETRY_DELAY)
            print(f"  Network error: {e} - retrying in {delay:.0f}s ...", file=sys.stderr)
            time.sleep(delay)
            return _request(url, token, method, body, content_type, _retries + 1)
        print(f"  Network error for {url}: {e}", file=sys.stderr)
        return None


def github_rest(path, token):
    url = path if path.startswith("http") else f"{GITHUB_API}/{path}"
    return _request(url, token)


def github_graphql(query, token):
    body = json.dumps({"query": query}).encode()
    raw = _request(GITHUB_GRAPHQL, token, method="POST", body=body, content_type="application/json")
    if not raw:
        return {}, []
    errors = []
    if "errors" in raw:
        for err in raw["errors"]:
            msg = err.get("message", "?")
            errors.append(msg)
            print(f"  GraphQL error: {msg}", file=sys.stderr)
    return raw.get("data") or {}, errors


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
    """Extract GitHub repo links from markdown and HTML text.

    Matches markdown links [text](https://github.com/owner/repo...) and
    HTML anchors <a href="https://github.com/owner/repo...">.  Sub-path
    links (owner/repo/tree/...) are normalised to owner/repo for dedup so
    monorepo-based awesome lists are counted correctly.
    """
    links = []
    seen = set()

    # Match both markdown [...](url) and HTML <a href="url"> patterns
    patterns = [
        r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:/[^)]*)?)\)",
        r'<a\s[^>]*href="https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:/[^"]*)?)"',
    ]

    for pat in patterns:
        for match in re.finditer(pat, text):
            # Markdown pattern has 2 groups, HTML has 1
            repo_path = match.group(match.lastindex)
            parts = repo_path.strip("/").split("/")
            if len(parts) < 2:
                continue
            owner_repo = f"{parts[0]}/{parts[1]}".lower()
            if parts[0].lower() in NOT_REPO_PREFIXES:
                continue
            if owner_repo not in seen:
                seen.add(owner_repo)
                links.append(f"{parts[0]}/{parts[1]}")
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


_HTML_ANCHOR_RE = re.compile(
    r'<a\s[^>]*href="https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:/[^"]*)?)">([^<]*)',
    re.IGNORECASE,
)


def parse_list_readme(readme_text, category_name, category_id, source_repo):
    """Extract repos from a list README with subcategory headings.

    Handles both standard markdown links ([name](url)) and HTML anchor tags
    (<a href="url">name</a>) since some lists use HTML tables or mixed markup.
    """
    repos = []
    seen = set()
    current_sub = "General"
    skip_sections = {"contents", "license", "contributing", "footnotes", "related", "about", "meta"}
    source_lower = source_repo.lower()

    def _add(repo_path, name):
        clean = repo_path.strip("/").split("?")[0].split("#")[0]
        parts = clean.split("/")
        if len(parts) < 2:
            return
        clean = f"{parts[0]}/{parts[1]}"
        key = clean.lower()
        if key == source_lower or key in seen:
            return
        owner = parts[0].lower()
        if owner in NOT_REPO_PREFIXES:
            return
        seen.add(key)
        repos.append({
            "full_name": clean,
            "link_name": name.strip() or clean.split("/")[1],
            "category": category_id,
            "category_name": category_name,
            "subcategory": current_sub,
            "subcategory_id": slugify(current_sub),
        })

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
            _add(repo_path, name)

        for repo_path, name in _HTML_ANCHOR_RE.findall(line):
            _add(repo_path, name)

    return repos


def is_noise_url(url):
    """Return True if the URL is a badge, image, social link, or other noise."""
    if not url or not url.startswith("http"):
        return True
    if NOISE_DOMAINS_RE.search(url):
        return True
    return bool(NOISE_PATHS_RE.search(url))


_NOISE_LINK_RE = re.compile(
    r"\[(All Versions|Preprint|Paper|Project|Website|Code|Homepage"
    r"|Slides|Video|Demo|Blog|Talk|Poster|Dataset|Models?)\]\([^)]*\)",
    re.IGNORECASE,
)


def _clean_resource_desc(desc):
    """Strip markdown formatting and noise link labels from a resource description."""
    desc = _NOISE_LINK_RE.sub("", desc)
    desc = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", desc)
    desc = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", desc)
    desc = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", desc)
    desc = re.sub(r"~~([^~]+)~~", r"\1", desc)
    desc = re.sub(r"(?:[.,:;]\s*){2,}", ". ", desc)
    desc = re.sub(r"\s{2,}", " ", desc)
    return desc.strip(" .-")


def extract_resource_links(readme_text, category_name, category_id, source_repo):
    """Extract non-GitHub resource links from a list's README."""
    resources = []
    current_sub = "General"
    skip_sections = {"contents", "license", "contributing", "footnotes",
                     "related", "about", "meta", "table of contents"}
    seen_urls = set()

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

        if not LIST_ITEM_RE.match(line):
            continue

        # Only extract the first non-noise, non-GitHub link per list item.
        # Secondary inline links ([All Versions], [paper], [Project], etc.)
        # are references/mirrors, not standalone resources.
        found = False
        for title, url in MARKDOWN_LINK_RE.findall(line):
            if found:
                break
            url = url.strip()
            if is_noise_url(url):
                continue
            if GITHUB_REPO_RE.match(url):
                continue
            url_lower = url.lower()
            if url_lower in seen_urls:
                continue
            seen_urls.add(url_lower)
            found = True

            desc = ""
            desc_match = RESOURCE_DESC_RE.match(line)
            if desc_match:
                desc = desc_match.group(1).strip()
                desc = _clean_resource_desc(desc)
            if len(desc) > 200:
                desc = desc[:197] + "..."

            resources.append({
                "url": url,
                "title": title.strip().lstrip("["),
                "description": desc,
                "category": category_id,
                "category_name": category_name,
                "subcategory": current_sub,
                "subcategory_id": slugify(current_sub),
                "source_repo": source_repo,
            })

    return resources


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
      isFork
      issues(states: OPEN) {{ totalCount }}
      pullRequests(states: OPEN) {{ totalCount }}
      watchers {{ totalCount }}
      primaryLanguage {{ name }}
      licenseInfo {{ spdxId }}
      pushedAt
      createdAt
      updatedAt
      hasWikiEnabled
      hasDiscussionsEnabled
      releases(last: 1) {{
        nodes {{ tagName publishedAt }}
      }}
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


# compute_health imported from shared.py


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

        # Latest release info
        latest_release = ""
        releases = (rd.get("releases") or {}).get("nodes", [])
        if releases:
            latest_release = releases[0].get("tagName", "")

        rec = {
            "full_name": nwo,
            "name": nwo.split("/")[1],
            "owner": nwo.split("/")[0],
            "description": (rd.get("description") or "")[:150],
            "stars": rd["stargazerCount"],
            "forks": rd["forkCount"],
            "open_issues": rd["issues"]["totalCount"],
            "open_prs": rd["pullRequests"]["totalCount"],
            "watchers": rd["watchers"]["totalCount"],
            "language": (rd.get("primaryLanguage") or {}).get("name", ""),
            "license": (rd.get("licenseInfo") or {}).get("spdxId", ""),
            "last_push": rd.get("pushedAt", ""),
            "created_at": rd.get("createdAt", ""),
            "updated_at": rd.get("updatedAt", ""),
            "is_archived": rd.get("isArchived", False),
            "is_fork": rd.get("isFork", False),
            "has_wiki": rd.get("hasWikiEnabled", False),
            "has_discussions": rd.get("hasDiscussionsEnabled", False),
            "latest_release": latest_release,
            "commits_90d": commits_90d,
            "topics": topics,
            "category": info["category"],
            "subcategory": info.get("subcategory", "General"),
            "subcategory_id": info.get("subcategory_id", "general"),
        }
        rec["health"] = compute_health(rec)
        rec["is_awesome_list"] = False
        rec["tier"] = info.get("tier", "non-canonical")
        repos.append(rec)

    return repos


def search_awesome_repos(token, exclude_set):
    """Search GitHub for repos with 'awesome' in name, not in canonical set.

    Uses multiple queries with different sort orders to widen discovery beyond
    the 1000-result GitHub API limit per query.
    """
    candidates = []
    seen = set()

    queries = [
        ("awesome in:name stars:>=" + str(MIN_STARS) + " fork:false", "stars", "desc"),
        ("awesome in:name stars:>=" + str(MIN_STARS) + " fork:false", "updated", "desc"),
        ("awesome in:name stars:>=" + str(MIN_STARS) + " fork:false", "stars", "asc"),
        ("topic:awesome-list stars:>=" + str(MIN_STARS) + " fork:false", "stars", "desc"),
        ("topic:curated-list stars:>=" + str(MIN_STARS) + " fork:false", "stars", "desc"),
        # Star-range buckets to fill the dead zone between asc/desc extremes
        ("awesome in:name stars:50..200 fork:false", "stars", "desc"),
        ("awesome in:name stars:200..350 fork:false", "stars", "desc"),
        ("awesome in:name stars:350..500 fork:false", "stars", "desc"),
        ("awesome in:name stars:500..750 fork:false", "stars", "desc"),
        ("awesome in:name stars:750..1000 fork:false", "stars", "desc"),
        ("awesome in:name stars:1000..2000 fork:false", "stars", "desc"),
        ("awesome in:name stars:2000..5000 fork:false", "stars", "desc"),
        ("awesome in:name stars:5000..50000 fork:false", "stars", "desc"),
    ]

    for query_str, sort_by, order in queries:
        encoded = quote(query_str)
        print(f"\n  Query: sort={sort_by} order={order}")

        is_topic_query = query_str.startswith("topic:")

        for page in range(1, SEARCH_PAGES + 1):
            url = f"{GITHUB_API}/search/repositories?q={encoded}&sort={sort_by}&order={order}&per_page=100&page={page}"
            print(f"    Page {page}/{SEARCH_PAGES}...", end="", flush=True)

            data = github_rest(url, token)
            if data is None:
                print(" FAILED (rate limit or network error - results may be incomplete)", file=sys.stderr)
                break
            if "items" not in data:
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

                # Name-based queries require "awesome" in the repo name;
                # topic-based queries already matched on topic so skip this check
                if not is_topic_query:
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
            time.sleep(SEARCH_DELAY)

            # Stop if fewer than 100 results (last page)
            if len(items) < 100:
                break

    return candidates


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch non-canonical awesome lists")
    parser.add_argument(
        "--force-search",
        action="store_true",
        help="Ignore any saved checkpoint and run the full search from scratch",
    )
    args = parser.parse_args()

    token = get_token()

    # Load existing canonical data
    if not REPO_DATA.exists():
        print("Error: repos.json not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    with REPO_DATA.open() as f:
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

    # Check for checkpoint from a previous interrupted run
    cp_stage, cp_data = load_checkpoint()
    resume = not args.force_search and cp_stage == "unofficial_done" and cp_data

    if args.force_search and cp_stage:
        print("  [checkpoint] --force-search: ignoring checkpoint, running full search")
        clear_checkpoint()

    if resume:
        print(f"\n  [checkpoint] Found checkpoint at '{cp_stage}' - skipping search and validation")
        unofficial = []
        noncanonical = cp_data["noncanonical"]
    else:
        # Step 1: Search GitHub for awesome-* repos
        print("\nSearching GitHub for awesome lists outside the official ecosystem...")
        candidates = search_awesome_repos(token, exclude_set)
        print(f"\n  {len(candidates)} candidate repos found")

        # Step 2: Validate candidates by checking their READMEs
        # Split into unofficial (has awesome badge) and non-canonical (no badge)
        print("\nValidating candidates (checking READMEs)...")
        unofficial = []
        noncanonical = []
        total_cands = len(candidates)
        validated_count = 0
        def _validate_candidate(idx_cand):
            nonlocal validated_count
            i, cand = idx_cand
            tag = f"[{i + 1}/{total_cands}]"
            fn = cand["full_name"]

            time.sleep(REST_DELAY)
            readme = fetch_repo_readme(fn, token)
            if not readme:
                print(f"  {tag} {fn}... no README", flush=True)
                return None

            has_badge = bool(AWESOME_BADGE_RE.search(readme))

            if has_badge:
                links = extract_github_links(readme)
                link_count = len(links)
                headings = len(re.findall(r"^#{2,4}\s+", readme, re.MULTILINE))
                if link_count < MIN_LINK_COUNT or headings < 2:
                    print(f"  {tag} {fn}... badge but too few links ({link_count})", flush=True)
                    return None
                print(f"  {tag} {fn}... unofficial ({link_count} links, badge)", flush=True)
                return ("unofficial", {
                    "full_name": fn,
                    "name": cand["name"],
                    "description": cand["description"],
                    "stars": cand["stars"],
                    "readme": readme,
                    "link_count": link_count,
                })
            is_list, link_count = looks_like_curated_list(readme)
            if not is_list:
                print(f"  {tag} {fn}... not a list ({link_count} links)", flush=True)
                return None
            print(f"  {tag} {fn}... non-canonical ({link_count} links)", flush=True)
            return ("noncanonical", {
                "full_name": fn,
                "name": cand["name"],
                "description": cand["description"],
                "stars": cand["stars"],
                "readme": readme,
                "link_count": link_count,
            })

        with ThreadPoolExecutor(max_workers=VALIDATION_WORKERS) as pool:
            for result in pool.map(_validate_candidate, enumerate(candidates)):
                if result is None:
                    continue
                tier, entry = result
                if tier == "unofficial":
                    unofficial.append(entry)
                else:
                    noncanonical.append(entry)

        print(f"\n  {len(unofficial)} unofficial lists (have badge, not in official repo)")
        print(f"  {len(noncanonical)} non-canonical lists (no badge)")

        if not unofficial and not noncanonical:
            print("No lists found. Exiting.")
            existing["unofficial_categories"] = []
            existing["non_canonical_categories"] = []
            with REPO_DATA.open("w") as f:
                json.dump(existing, f, separators=(",", ":"))
            return

    # Helper to crawl a list of validated entries and produce repos + resources
    def crawl_lists(validated, tier_label):
        links = []
        resources = []
        cat_meta = {}
        for v in validated:
            cid = slugify(v["name"])
            cname = v["name"].replace("-", " ").replace("awesome ", "").replace("Awesome ", "").title()
            if cid in cat_meta:
                cid = slugify(v["full_name"].replace("/", "-"))
            cat_meta[cid] = {
                "name": cname,
                "source_repo": v["full_name"],
                "description": v["description"],
                "stars": v["stars"],
                "link_count": v["link_count"],
            }
            parsed = parse_list_readme(v["readme"], cname, cid, v["full_name"])
            res = extract_resource_links(v["readme"], cname, cid, v["full_name"])
            print(f"  {v['full_name']}: {len(parsed)} repos, {len(res)} resources -> {cname}")
            links.extend(parsed)
            resources.extend(res)
        return links, resources, cat_meta

    # Helper to batch-fetch via GraphQL and build category summaries
    def fetch_and_summarize(all_links, cat_meta, tier_label, dedup_seed, resolve_redirects=True):
        # Build existing-repo health lookup so deduped entries can still
        # contribute to the category health filter.
        existing_health = {r["full_name"].lower(): r.get("health", 0) for r in existing.get("repos", [])}

        seen = set(dedup_seed)
        unique = []
        # Track per-category supplemental health for repos already in DB
        cat_known_health = {}  # cid -> [health, ...]
        for link in all_links:
            key = link["full_name"].lower()
            if key not in seen:
                seen.add(key)
                link["tier"] = tier_label
                unique.append(link)
            else:
                # Repo already in DB - note its health for the category filter
                cid = link["category"]
                h = existing_health.get(key, 0)
                cat_known_health.setdefault(cid, []).append(h)
        print(f"\n  {len(unique)} unique {tier_label} project repos")

        if not unique:
            return [], [], seen

        print(f"\nFetching GitHub metrics for {tier_label} repos...")
        total_batches = (len(unique) + BATCH_SIZE - 1) // BATCH_SIZE
        batches = []
        for bn in range(total_batches):
            start = bn * BATCH_SIZE
            batches.append((bn, unique[start:start + BATCH_SIZE]))

        def _fetch_gql_batch(batch_num_info):
            bn, batch = batch_num_info
            query = build_graphql_query(batch)
            data, _errors = github_graphql(query, token)
            repos = process_batch_result(data, batch)
            failed = not data
            resolved_names = {r["full_name"].lower() for r in repos}
            missed = [info for info in batch if info["full_name"].lower() not in resolved_names]
            return bn, batch, repos, failed, missed

        gql_results = [None] * total_batches
        all_missed = []
        with ThreadPoolExecutor(max_workers=GQL_WORKERS) as pool:
            futures = {pool.submit(_fetch_gql_batch, b): b[0] for b in batches}
            for future in as_completed(futures):
                bn, batch, repos, failed, missed = future.result()
                gql_results[bn] = repos
                all_missed.extend(missed)
                label = "FAILED" if failed else f"{len(repos)} repos"
                print(f"  Batch {bn + 1}/{total_batches} done ({label})", flush=True)

        # Retry failed batches sequentially with escalating cooldown
        prev_failed_count = None
        for attempt in range(1, BATCH_RETRIES + 1):
            failed_indices = [i for i, r in enumerate(gql_results) if r is not None and len(r) == 0]
            retry_batches = [(i, batches[i][1]) for i in failed_indices if len(batches[i][1]) > 0]
            if not retry_batches:
                break
            # Early exit: if previous round recovered nothing, stop retrying
            if prev_failed_count is not None and len(retry_batches) >= prev_failed_count:
                print("  No batches recovered in previous round - skipping remaining retries", flush=True)
                break
            prev_failed_count = len(retry_batches)
            cooldown = GQL_DELAY * (2 ** attempt)
            print(f"  Retrying {len(retry_batches)} failed batches (round {attempt}/{BATCH_RETRIES}, {cooldown:.0f}s cooldown)...", flush=True)
            time.sleep(cooldown)
            for idx, batch in retry_batches:
                time.sleep(GQL_DELAY)
                query = build_graphql_query(batch)
                data, _errors = github_graphql(query, token)
                repos = process_batch_result(data, batch)
                if repos:
                    gql_results[idx] = repos
                    print(f"    Batch {idx + 1} recovered ({len(repos)} repos)", flush=True)

        still_failed = [i for i, r in enumerate(gql_results) if r is not None and len(r) == 0 and len(batches[i][1]) > 0]
        if still_failed:
            lost = sum(len(batches[i][1]) for i in still_failed)
            print(f"  WARNING: {len(still_failed)} batches permanently failed ({lost} repos lost)", file=sys.stderr)

        fetched = []
        for repos in gql_results:
            if repos:
                fetched.extend(repos)

        # Recover renamed/transferred repos via REST API redirect
        if all_missed and resolve_redirects:
            resolved_already = {r["full_name"].lower() for r in fetched}
            to_resolve = [info for info in all_missed if info["full_name"].lower() not in resolved_already]
            if to_resolve:
                print(f"\n  Resolving {len(to_resolve)} unresolved repos via REST API...")
                redirected = []
                for idx, info in enumerate(to_resolve, 1):
                    if idx % 200 == 0 or idx == len(to_resolve):
                        print(f"    [{idx}/{len(to_resolve)}] checked...", flush=True)
                    time.sleep(0.75)
                    rest = github_rest(f"repos/{info['full_name']}", token)
                    if rest and rest.get("full_name"):
                        new_name = rest["full_name"]
                        if new_name.lower() != info["full_name"].lower():
                            print(f"    {info['full_name']} -> {new_name}", flush=True)
                            redir_info = dict(info)
                            redir_info["full_name"] = new_name
                            redirected.append(redir_info)
                if redirected:
                    print(f"  Re-querying {len(redirected)} redirected repos...")
                    redir_batches = [redirected[i:i + BATCH_SIZE] for i in range(0, len(redirected), BATCH_SIZE)]
                    for rb in redir_batches:
                        time.sleep(GQL_DELAY)
                        query = build_graphql_query(rb)
                        data, _errors = github_graphql(query, token)
                        repos = process_batch_result(data, rb)
                        if repos:
                            fetched.extend(repos)
                            print(f"    Recovered {len(repos)} renamed repos", flush=True)
                dead = len(to_resolve) - len(redirected)
                if dead:
                    print(f"  {dead} repos truly gone (deleted or private)")
        elif all_missed and not resolve_redirects:
            print(f"  Skipping redirect resolution for {len(all_missed)} missed project repos")

        # Compute category stats and filter by health
        # Health is computed over ALL repos a list references (unique + already-known)
        # so that deduplication against the official DB doesn't penalise quality lists.
        print(f"\nComputing {tier_label} category statistics...")
        cd_map = {}
        for r in fetched:
            c = r["category"]
            if c not in cd_map:
                cd_map[c] = {"repos": [], "health_sum": 0, "health_count": 0, "langs": {}}
            cd_map[c]["repos"].append(r)
            cd_map[c]["health_sum"] += r.get("health", 0)
            cd_map[c]["health_count"] += 1
            lang = r.get("language", "")
            if lang:
                cd_map[c]["langs"][lang] = cd_map[c]["langs"].get(lang, 0) + 1

        # Supplement health counts with already-known repos from the DB
        for cid, known_scores in cat_known_health.items():
            if cid not in cd_map:
                continue
            cd_map[cid]["health_sum"] += sum(known_scores)
            cd_map[cid]["health_count"] += len(known_scores)

        categories = []
        kept = []
        dropped = 0
        for cid, cd in cd_map.items():
            count = len(cd["repos"])  # stored repos (unique only)
            health_count = cd["health_count"]  # includes already-known repos
            if health_count == 0:
                continue
            avg_health = round(cd["health_sum"] / health_count)
            if avg_health < MIN_HEALTH:
                dropped += 1
                continue
            meta = cat_meta.get(cid, {})
            top_langs = sorted(cd["langs"].items(), key=lambda x: -x[1])[:5]
            sub_ids = {r.get("subcategory_id", "general") for r in cd["repos"]}
            categories.append({
                "id": cid,
                "name": meta.get("name", cid.replace("-", " ").title()),
                "count": count,
                "source_repo": meta.get("source_repo", ""),
                "avg_health": avg_health,
                "is_awesome_list": tier_label == "unofficial",
                "tier": tier_label,
                "subcategory_count": len(sub_ids),
                "top_languages": [{"name": name, "count": c} for name, c in top_langs],
            })
            kept.extend(cd["repos"])

        categories.sort(key=lambda c: c["name"])
        print(f"  {len(categories)} {tier_label} categories pass health filter (dropped {dropped})")
        print(f"  {len(kept)} repos in qualifying categories")
        return categories, kept, seen

    if resume:
        print(f"\n  [checkpoint] Resuming from '{cp_stage}' - skipping steps 1-3")
        uo_cats = cp_data["uo_cats"]
        uo_repos = cp_data["uo_repos"]
        uo_resources = cp_data["uo_resources"]
        uo_seen = set(cp_data["uo_seen"])
        print(f"  Restored: {len(uo_cats)} unofficial categories, {len(uo_repos)} unofficial repos")
        print(f"  {len(noncanonical)} non-canonical lists to process")
    else:
        # Step 3: Crawl unofficial lists
        if unofficial:
            print("\nCrawling unofficial lists for repos...")
            uo_links, uo_resources, uo_meta = crawl_lists(unofficial, "unofficial")
        else:
            uo_links, uo_resources, uo_meta = [], [], {}

        uo_cats, uo_repos, uo_seen = fetch_and_summarize(uo_links, uo_meta, "unofficial", exclude_set)

        save_checkpoint("unofficial_done", {
            "noncanonical": noncanonical,
            "uo_cats": uo_cats,
            "uo_repos": uo_repos,
            "uo_resources": uo_resources,
            "uo_seen": list(uo_seen),
        })

    # Step 4: Crawl non-canonical lists
    if noncanonical:
        print("\nCrawling non-canonical lists for repos...")
        nc_links, nc_resources, nc_meta = crawl_lists(noncanonical, "non-canonical")
    else:
        nc_links, nc_resources, nc_meta = [], [], {}

    nc_cats, nc_repos, _ = fetch_and_summarize(nc_links, nc_meta, "non-canonical", uo_seen, resolve_redirects=False)

    # Step 5: Write back to repos.json
    existing["unofficial_categories"] = uo_cats
    existing["non_canonical_categories"] = nc_cats

    # Replace old non-official repos and add new ones
    existing_repos = existing.get("repos", [])
    existing_repos = [r for r in existing_repos if r.get("tier", "official") == "official"]
    all_new = sorted(uo_repos + nc_repos, key=lambda r: -r["stars"])
    existing_repos.extend(all_new)
    existing["repos"] = existing_repos

    # Drop resources whose category was removed by the health filter
    surviving_cats = {c["id"] for c in uo_cats} | {c["id"] for c in nc_cats}
    uo_resources = [r for r in uo_resources if r.get("category") in surviving_cats]
    nc_resources = [r for r in nc_resources if r.get("category") in surviving_cats]

    # Deduplicate and merge resources
    all_new_resources = uo_resources + nc_resources
    existing_resources = existing.get("resources", [])
    seen_urls = {r["url"].lower() for r in existing_resources}
    added_res = []
    for res in all_new_resources:
        url_key = res["url"].lower()
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            added_res.append(res)
    existing_resources.extend(added_res)
    existing["resources"] = existing_resources

    # Update meta
    existing["meta"]["total_repos"] = len(existing_repos)
    existing["meta"]["total_resources"] = len(existing_resources)

    with REPO_DATA.open("w") as f:
        json.dump(existing, f, separators=(",", ":"))

    clear_checkpoint()
    size_mb = REPO_DATA.stat().st_size / 1024 / 1024
    print("\nDone.")
    print(f"  Unofficial: {len(uo_cats)} lists, {len(uo_repos)} repos")
    print(f"  Non-canonical: {len(nc_cats)} lists, {len(nc_repos)} repos")
    print(f"  Resources added: {len(added_res)}")
    print(f"  Output: {REPO_DATA} ({size_mb:.1f}MB)")
    print(f"  Total repos in dataset: {len(existing_repos)} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
