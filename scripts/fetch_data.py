#!/usr/bin/env python3
"""Awesome Visualizer - Data Pipeline (Deep Crawl)

Recursive crawl with awesome badge detection:
1. Fetch sindresorhus/awesome README -> discover awesome sub-list repos
2. For each sub-list, fetch its README -> verify awesome badge -> discover repos
3. Identify nested awesome lists (badge + topic/name heuristics) -> recurse
4. Batch-query GitHub GraphQL API for metrics on all discovered repos
5. Write site/data/repos.json

An awesome list is any repo whose README contains the awesome.re badge.
Crawl depth is limited to MAX_CRAWL_DEPTH levels.

Usage:
    nix develop --command python scripts/fetch_data.py

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

GITHUB_GRAPHQL = "https://api.github.com/graphql"
GITHUB_API = "https://api.github.com"
MASTER_LIST = "sindresorhus/awesome"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "site" / "data" / "repos.json"
CHECKPOINT_FILE = Path(__file__).resolve().parent.parent / "site" / "data" / ".fetch_checkpoint.json"
NINETY_DAYS_AGO = (datetime.now(UTC) - timedelta(days=90)).isoformat()
MAX_SUBLISTS = 800
REST_DELAY = 0.3
README_WORKERS = 15
GQL_WORKERS = 2
AWESOME_BADGE_RE = re.compile(r"awesome\.re/badge", re.IGNORECASE)
MAX_CRAWL_DEPTH = 3

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
    with open(tmp, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    Path(tmp).replace(CHECKPOINT_FILE)
    size_mb = CHECKPOINT_FILE.stat().st_size / 1024 / 1024
    print(f"  [checkpoint] Saved at stage '{stage}' ({size_mb:.1f}MB)")


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
    """Read GITHUB_TOKEN from environment, falling back to `gh auth token`."""
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


def _request(url, token, method="GET", body=None, content_type=None, _retries=0):
    """Make an authenticated HTTP request to GitHub with retry logic."""
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
        if e.code in (500, 502, 503, 504) and _retries < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** _retries) + random.uniform(0, RETRY_DELAY)
            print(f"  HTTP {e.code} - retrying in {delay:.0f}s (attempt {_retries + 1}/{MAX_RETRIES}) ...", file=sys.stderr)
            time.sleep(delay)
            return _request(url, token, method, body, content_type, _retries + 1)
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except (TimeoutError, OSError, HTTPException) as e:
        if _retries < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** _retries) + random.uniform(0, RETRY_DELAY)
            print(f"  Network error: {e} - retrying in {delay:.0f}s (attempt {_retries + 1}/{MAX_RETRIES}) ...", file=sys.stderr)
            time.sleep(delay)
            return _request(url, token, method, body, content_type, _retries + 1)
        print(f"  Network error for {url}: {e}", file=sys.stderr)
        return None


def github_rest(path, token):
    """GET from GitHub REST API."""
    url = path if path.startswith("http") else f"{GITHUB_API}/{path}"
    return _request(url, token)


def github_graphql(query, token):
    """POST a GraphQL query to GitHub."""
    body = json.dumps({"query": query}).encode()
    raw = _request(GITHUB_GRAPHQL, token, method="POST", body=body, content_type="application/json")
    if not raw:
        return {}, []
    errors = []
    if "errors" in raw:
        for err in raw["errors"]:
            msg = err.get("message", "unknown error")
            errors.append(msg)
            print(f"  GraphQL error: {msg}", file=sys.stderr)
    return raw.get("data") or {}, errors


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


def has_awesome_badge(readme_text):
    """Check if a README contains the awesome.re badge."""
    if not readme_text:
        return False
    return bool(AWESOME_BADGE_RE.search(readme_text))


def looks_like_awesome_list(name, full_name):
    """Quick heuristic for potential awesome lists -- no API call needed."""
    n = (name or "").lower()
    fn = full_name.lower().split("/")[-1] if full_name else ""
    return n.startswith("awesome") or fn.startswith("awesome")


def extract_github_repo_links(text):
    """Extract [name](github.com/owner/repo) links from markdown."""
    links = []
    for name, repo_path in re.findall(
        r"\[([^\]]+)\]\(https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
        text,
    ):
        clean = repo_path.strip("/")
        if clean.count("/") == 1:
            owner = clean.split("/")[0].lower()
            if owner in NOT_REPO_PREFIXES:
                continue
            links.append({"full_name": clean, "link_name": name})
    return links


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
    # Remove noise markdown links entirely (before link-to-text)
    desc = _NOISE_LINK_RE.sub("", desc)
    # Convert remaining markdown links to plain text
    desc = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", desc)
    # Strip bold/italic markers: ***text***, **text**, *text*
    desc = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", desc)
    # Strip _underline_ and ~~strikethrough~~ markers
    desc = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", desc)
    desc = re.sub(r"~~([^~]+)~~", r"\1", desc)
    # Collapse orphaned punctuation and whitespace
    desc = re.sub(r"(?:[.,:;]\s*){2,}", ". ", desc)
    desc = re.sub(r"\s{2,}", " ", desc)
    return desc.strip(" .-")


def extract_resource_links(readme_text, category_name, category_id, source_repo):
    """Extract non-GitHub resource links from a sub-list's README.

    Returns a list of resource dicts with url, title, description, category,
    subcategory, and source_repo.
    """
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
            # Skip GitHub repo links (already handled by parse_sublist_readme)
            if GITHUB_REPO_RE.match(url):
                continue
            url_lower = url.lower()
            if url_lower in seen_urls:
                continue
            seen_urls.add(url_lower)
            found = True

            # Extract description from text after the link
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
                owner = clean.split("/")[0].lower()
                if owner in NOT_REPO_PREFIXES:
                    continue
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


_HTML_ANCHOR_RE = re.compile(
    r'<a\s[^>]*href="https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:/[^"]*)?)">([^<]*)',
    re.IGNORECASE,
)


def parse_sublist_readme(readme_text, category_name, category_id, source_repo):
    """Extract individual project repos from a sub-list's README with subcategory headings.

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
            _add(repo_path, name)

        for repo_path, name in _HTML_ANCHOR_RE.findall(line):
            _add(repo_path, name)

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
        rec["is_awesome_list"] = "awesome-list" in topics or "awesome" in topics
        rec["tier"] = "official"
        repos.append(rec)

    return repos


def main():
    token = get_token()

    # ---- Check for checkpoint from a previous interrupted run ----
    cp_stage, cp_data = load_checkpoint()

    if cp_stage == "crawl_done":
        print(f"\n  [checkpoint] Resuming from '{cp_stage}' - skipping steps 1-3")
        unique = cp_data["unique"]
        all_resources = cp_data["all_resources"]
        cat_meta = cp_data["cat_meta"]
        crawled_as_list = set(cp_data["crawled_as_list"])
        seen = {link["full_name"].lower() for link in unique}
        print(f"  Restored {len(unique)} unique links, {len(all_resources)} resources, {len(cat_meta)} categories")
    elif cp_stage == "gql_done":
        print(f"\n  [checkpoint] Resuming from '{cp_stage}' - skipping steps 1-5")
        unique = cp_data["unique"]
        all_repos = cp_data["all_repos"]
        all_resources = cp_data["all_resources"]
        cat_meta = cp_data["cat_meta"]
        crawled_as_list = set(cp_data["crawled_as_list"])
        seen = {link["full_name"].lower() for link in unique}
        print(f"  Restored {len(all_repos)} repos, {len(all_resources)} resources")
    elif cp_stage == "discovery_done":
        print(f"\n  [checkpoint] Resuming from '{cp_stage}' - skipping to output")
        all_repos = cp_data["all_repos"]
        all_resources = cp_data["all_resources"]
        cat_meta = cp_data["cat_meta"]
        seen = {r["full_name"].lower() for r in all_repos}
        print(f"  Restored {len(all_repos)} repos, {len(all_resources)} resources")
    else:
        cp_stage = None  # No valid checkpoint

    # ---- Steps 1-3: Fetch master + crawl sublists ----
    if not cp_stage:
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

        # Step 3: Crawl each sub-list for project repos (parallel)
        print("\nCrawling sub-lists for project repos...")
        all_links = []
        all_resources = []
        cat_meta = {}  # category_id -> {name, source_repo, url, is_awesome_list}
        crawled_as_list = {MASTER_LIST.lower()}
        for sl in sublists:
            crawled_as_list.add(sl["full_name"].lower())

        def _fetch_sublist(idx_sl):
            idx, sl = idx_sl
            subreadme = fetch_repo_readme(sl["full_name"], token)
            return idx, sl, subreadme

        sublist_results = [None] * len(sublists)
        with ThreadPoolExecutor(max_workers=README_WORKERS) as pool:
            futures = {pool.submit(_fetch_sublist, (i, sl)): i for i, sl in enumerate(sublists)}
            for future in as_completed(futures):
                idx, sl, subreadme = future.result()
                sublist_results[idx] = (sl, subreadme)

        for i, (sl, subreadme) in enumerate(sublist_results):
            tag = f"[{i + 1}/{len(sublists)}]"
            cid = sl["category_id"]

            if not subreadme:
                print(f"  {tag} {sl['full_name']} ({sl['category_name']})... SKIP")
                cat_meta[cid] = {
                    "name": sl["category_name"],
                    "source_repo": sl["full_name"],
                    "url": f"https://github.com/{sl['full_name']}",
                    "is_awesome_list": False,
                }
                continue

            is_awesome = has_awesome_badge(subreadme)
            cat_meta[cid] = {
                "name": sl["category_name"],
                "source_repo": sl["full_name"],
                "url": f"https://github.com/{sl['full_name']}",
                "is_awesome_list": is_awesome,
            }

            links = parse_sublist_readme(subreadme, sl["category_name"], cid, sl["full_name"])
            resources = extract_resource_links(subreadme, sl["category_name"], cid, sl["full_name"])
            badge_tag = "awesome" if is_awesome else "no badge"
            print(f"  {tag} {sl['full_name']} ({sl['category_name']})... {len(links)} repos, {len(resources)} resources [{badge_tag}]")
            all_links.extend(links)
            all_resources.extend(resources)

        # Step 4: Deduplicate (first-seen category wins)
        seen = set()
        unique = []
        for link in all_links:
            key = link["full_name"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(link)

        print(f"\n  {len(unique)} unique project repos after deduplication")

        # -- Save point: crawl complete --
        save_checkpoint("crawl_done", {
            "unique": unique,
            "all_resources": all_resources,
            "cat_meta": cat_meta,
            "crawled_as_list": sorted(crawled_as_list),
        })

    # Helper used by both step 5 and step 5b
    def _fetch_gql_batch(batch_num_info):
        bn, batch = batch_num_info
        query = build_graphql_query(batch)
        data, _errors = github_graphql(query, token)
        repos = process_batch_result(data, batch)
        failed = not data  # True if the request returned nothing
        # Track repos that got no GraphQL result (deleted/renamed/private)
        resolved_names = {r["full_name"].lower() for r in repos}
        missed = [info for info in batch if info["full_name"].lower() not in resolved_names]
        return bn, batch, repos, failed, missed

    # ---- Step 5: Batch query GraphQL for metrics ----
    if cp_stage in ("gql_done", "discovery_done"):
        print(f"\n  [checkpoint] Skipping GraphQL fetch (already done)")
    else:
        print("\nFetching GitHub metrics...")
        all_repos = []
        total_batches = (len(unique) + BATCH_SIZE - 1) // BATCH_SIZE
        batches = []
        for batch_num in range(total_batches):
            start = batch_num * BATCH_SIZE
            batches.append((batch_num, unique[start : start + BATCH_SIZE]))

        gql_results = [None] * total_batches
        all_missed = []  # repos that got no GraphQL result
        with ThreadPoolExecutor(max_workers=GQL_WORKERS) as pool:
            futures = {pool.submit(_fetch_gql_batch, b): b[0] for b in batches}
            for future in as_completed(futures):
                bn, batch, repos, failed, missed = future.result()
                gql_results[bn] = repos
                all_missed.extend(missed)
                label = "FAILED" if failed else f"{len(repos)} repos"
                print(f"  Batch {bn + 1}/{total_batches} done ({label})", flush=True)

        # Retry failed batches sequentially with escalating cooldown
        for attempt in range(1, BATCH_RETRIES + 1):
            failed_indices = [i for i, r in enumerate(gql_results) if r is not None and len(r) == 0]
            retry_batches = [(i, batches[i][1]) for i in failed_indices if len(batches[i][1]) > 0]
            if not retry_batches:
                break
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

        for repos in gql_results:
            if repos:
                all_repos.extend(repos)

        # Recover renamed/transferred repos via REST API redirect
        if all_missed:
            resolved_already = {r["full_name"].lower() for r in all_repos}
            to_resolve = [info for info in all_missed if info["full_name"].lower() not in resolved_already]
            if to_resolve:
                print(f"\nResolving {len(to_resolve)} unresolved repos via REST API...")
                redirected = []
                for info in to_resolve:
                    time.sleep(REST_DELAY)
                    rest = github_rest(f"repos/{info['full_name']}", token)
                    if rest and rest.get("full_name"):
                        new_name = rest["full_name"]
                        if new_name.lower() != info["full_name"].lower():
                            print(f"  {info['full_name']} -> {new_name}", flush=True)
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
                            all_repos.extend(repos)
                            print(f"    Recovered {len(repos)} renamed repos", flush=True)
                dead = len(to_resolve) - len(redirected)
                if dead:
                    print(f"  {dead} repos truly gone (deleted or private)")

        # -- Save point: GraphQL fetch complete --
        save_checkpoint("gql_done", {
            "unique": unique,
            "all_repos": all_repos,
            "all_resources": all_resources,
            "cat_meta": cat_meta,
            "crawled_as_list": sorted(crawled_as_list),
        })

    # ---- Step 5b: Recursive awesome list discovery ----
    if cp_stage in ("gql_done",):
        all_missed = []  # Not carried across checkpoints; only used within a run
    if cp_stage == "discovery_done":
        print("\n  [checkpoint] Skipping recursive discovery (already done)")
    else:
        print("\nDiscovering nested awesome lists...")
        depth = 2
        while depth <= MAX_CRAWL_DEPTH:
            potential = []
            for r in all_repos:
                fn_lower = r["full_name"].lower()
                if fn_lower in crawled_as_list:
                    continue
                crawled_as_list.add(fn_lower)
                is_awesome = r.get("is_awesome_list", False)
                if not is_awesome and not looks_like_awesome_list(r.get("name", ""), r["full_name"]):
                    continue
                potential.append(r)

            if not potential:
                print(f"  No candidates at depth {depth}")
                break

            # Fetch READMEs in parallel
            def _fetch_candidate_readme(repo):
                subreadme = fetch_repo_readme(repo["full_name"], token)
                return repo, subreadme

            candidates = []
            with ThreadPoolExecutor(max_workers=README_WORKERS) as pool:
                for r, subreadme in pool.map(_fetch_candidate_readme, potential):
                    if not subreadme or not has_awesome_badge(subreadme):
                        r["is_awesome_list"] = False
                        continue
                    r["is_awesome_list"] = True
                    candidates.append((r, subreadme))

            if not candidates:
                print(f"  No new awesome lists at depth {depth}")
                break

            print(f"  Found {len(candidates)} awesome lists at depth {depth}")
            new_links = []
            for r, subreadme in candidates:
                cid = slugify(r.get("name", r["full_name"].split("/")[1]))
                cname = r.get("link_name", r.get("name", ""))
                links = parse_sublist_readme(subreadme, cname, cid, r["full_name"])
                resources = extract_resource_links(subreadme, cname, cid, r["full_name"])
                new_links.extend(links)
                all_resources.extend(resources)
                cat_meta[cid] = {
                    "name": cname,
                    "source_repo": r["full_name"],
                    "url": f"https://github.com/{r['full_name']}",
                    "is_awesome_list": True,
                }

            new_unique = []
            for link in new_links:
                key = link["full_name"].lower()
                if key not in seen:
                    seen.add(key)
                    new_unique.append(link)

            if not new_unique:
                print(f"  No new repos from depth {depth} awesome lists")
                break

            print(f"  {len(new_unique)} new repos to fetch")
            total_new = (len(new_unique) + BATCH_SIZE - 1) // BATCH_SIZE
            new_batches = []
            for bn in range(total_new):
                start = bn * BATCH_SIZE
                new_batches.append((bn, new_unique[start:start + BATCH_SIZE]))

            new_gql_results = [None] * total_new
            with ThreadPoolExecutor(max_workers=GQL_WORKERS) as pool:
                futures = {pool.submit(_fetch_gql_batch, b): b[0] for b in new_batches}
                for future in as_completed(futures):
                    bn, batch, repos, failed, missed = future.result()
                    new_gql_results[bn] = repos
                    all_missed.extend(missed)
                    label = "FAILED" if failed else f"{len(repos)} repos"
                    print(f"    Batch {bn + 1}/{total_new} done ({label})", flush=True)

            for attempt in range(1, BATCH_RETRIES + 1):
                failed_indices = [i for i, r in enumerate(new_gql_results) if r is not None and len(r) == 0]
                retry_batches = [(i, new_batches[i][1]) for i in failed_indices if len(new_batches[i][1]) > 0]
                if not retry_batches:
                    break
                print(f"    Retrying {len(retry_batches)} failed batches (attempt {attempt}/{BATCH_RETRIES})...", flush=True)
                for idx, batch in retry_batches:
                    time.sleep(GQL_DELAY)
                    query = build_graphql_query(batch)
                    data, _errors = github_graphql(query, token)
                    repos = process_batch_result(data, batch)
                    if repos:
                        new_gql_results[idx] = repos
                        print(f"      Batch {idx + 1} recovered ({len(repos)} repos)", flush=True)

            for repos in new_gql_results:
                if repos:
                    all_repos.extend(repos)

            depth += 1

        print(f"\n  Total repos after discovery: {len(all_repos)}")

        # -- Save point: all fetching complete --
        save_checkpoint("discovery_done", {
            "all_repos": all_repos,
            "all_resources": all_resources,
            "cat_meta": cat_meta,
        })

    # ---- Step 6: Build output ----
    seen_urls = set()
    unique_resources = []
    for res in all_resources:
        url_key = res["url"].lower()
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            unique_resources.append(res)

    print(f"  {len(unique_resources)} unique resource links extracted")

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
            "avg_health": avg_health,
            "is_awesome_list": meta.get("is_awesome_list", False),
            "tier": "official",
            "subcategory_count": len(cat_subcats.get(cid, set())),
            "top_languages": [{"name": name, "count": c} for name, c in top_langs],
        })
    # Add resource-only categories: lists whose repos were all deduped away
    # but still contributed resource links.
    res_cat_ids = set()
    for res in unique_resources:
        res_cat_ids.add(res.get("category", ""))
    existing_cat_ids = {c["id"] for c in categories}
    for cid in sorted(res_cat_ids - existing_cat_ids):
        meta = cat_meta.get(cid)
        if not meta:
            continue
        categories.append({
            "id": cid,
            "name": meta.get("name", cid.replace("-", " ").title()),
            "count": 0,
            "source_repo": meta.get("source_repo", ""),
            "avg_health": 0,
            "is_awesome_list": meta.get("is_awesome_list", False),
            "tier": "official",
            "subcategory_count": 0,
            "top_languages": [],
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
            "last_updated": datetime.now(UTC).isoformat(),
            "total_repos": len(all_repos),
            "total_resources": len(unique_resources),
            "source": f"https://github.com/{MASTER_LIST}",
        },
        "categories": categories,
        "subcategories": subcategories,
        "languages": languages,
        "repos": sorted(all_repos, key=lambda r: -r["stars"]),
        "resources": unique_resources,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024
    print(f"\nDone. {len(all_repos)} repos, {len(unique_resources)} resources written to {OUTPUT_PATH} ({size_mb:.1f}MB)")

    # Clean up checkpoint after successful completion
    clear_checkpoint()


if __name__ == "__main__":
    main()
