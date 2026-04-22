<p align="center">
  <img src="site/logo.svg" alt="Awesome Visualizer logo" width="200">
</p>

<h1 align="center">Awesome Visualizer</h1>

<h3 align="center">

![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Hosting](https://img.shields.io/badge/hosting-GitHub%20Pages-blue)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Data refresh](https://img.shields.io/badge/data%20refresh-weekly%20(Wed)-brightgreen)
![Built with Nix](https://img.shields.io/badge/built%20with-Nix-5277C3?logo=nixos&logoColor=white)

</h3>

<h4 align="center">
  Consider supporting:<br><br>
  <a href="https://www.patreon.com/8153512/join">
    <img src="https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white" alt="Patreon">
  </a>
  <a href="https://github.com/sponsors/stradichenko">
    <img src="https://img.shields.io/badge/sponsor-30363D?style=for-the-badge&logo=GitHub-Sponsors&logoColor=#EA4AAA" alt="GitHub Sponsors">
  </a>
  <a href="https://buymeacoffee.com/stradichenko">
    <img src="https://raw.githubusercontent.com/pachadotdev/buymeacoffee-badges/main/bmc-donate-white.svg" alt="Buy Me A Coffee">
  </a>
</h4>

<h4 align="center">

[![Share on X](https://img.shields.io/badge/-Share%20on%20X-gray?style=flat&logo=x)](https://x.com/intent/tweet?text=Explore%20the%20awesome%20ecosystem%20-%20browse%2C%20search%2C%20and%20compare%2010%2C000%2B%20repos%20with%20health%20scores%20and%20visualizations.&url=https://github.com/stradichenko/awesome-visualizer&hashtags=awesome,github,opensource)

</h4>

<h3 align="center">

[Site!](https://stradichenko.github.io/awesome-visualizer/)

</h3>

A data-driven explorer for the [sindresorhus/awesome](https://github.com/sindresorhus/awesome) ecosystem. Browse, search, filter, and compare awesome list repositories with rich metrics -- stars, forks, commit activity, health scores -- all on a fast static site hosted on GitHub Pages.

## Features

- Filterable card grid and table views
- Full-text client-side search across repo names, descriptions, and topics
- Filter by category, language, and health score
- Sort by stars, health, recent activity, commits, or name
- Health score (0-100) combining stars, commit freshness, activity, and community signals
- Weekly data refresh via GitHub Actions (Wednesdays, 02:00 UTC)
- Dark-first design, fully responsive, no external dependencies

## How categories are built

A **category** in the site is one curated awesome list. Every category page shows the repos that list recommends, grouped under the same subcategory headings the original README uses.

### Discovery

A list becomes a category if it makes it through three stages:

1. **Discovery** - the list is found either by recursively crawling [sindresorhus/awesome](https://github.com/sindresorhus/awesome) (depth 3) or by querying GitHub Search for repos matching `awesome in:name`, the `awesome-list` topic, or the `curated-list` topic.
2. **Validation** - the list's README is fetched and inspected. To pass, it must contain at least 10 GitHub repository links and at least 2 section headings (`##` to `####`). Lists carrying the [![Awesome](https://awesome.re/badge.svg)](https://awesome.re) badge are routed to the official or unofficial tier; lists without the badge but with link-density indicators of a curated resource list are routed to non-canonical.
3. **Quality filter** - the linked repos are fetched in batches and a category-level health score is computed (mean health of every repo the list references, including ones already in our DB). Categories with average health below 50 are dropped. This keeps spam, abandoned plugin dumps, and starter-template lists out.

### Tiers

Each surviving list is placed into one of three tiers, which control how the site labels and groups it.

| Tier | Source | Has awesome.re badge | Discovery method |
| ---- | ------ | -------------------- | ---------------- |
| Official | sindresorhus/awesome subtree | yes | recursive crawl |
| Unofficial | community awesome list | yes | GitHub Search |
| Non-canonical | curated topic list | no | GitHub Search |

- **Official** - lists reachable from the canonical [sindresorhus/awesome](https://github.com/sindresorhus/awesome) index, recursively up to depth 3. These follow the official curation conventions and have been manually accepted upstream.
- **Unofficial** - lists carrying the awesome.re badge but not linked from the official index. They follow the same conventions; they just haven't been submitted or accepted into the master list.
- **Non-canonical** - lists that look like curated resource collections (10+ links, multiple section headings, good link density) but do not carry the awesome.re badge. Often topic lists that predate or simply don't follow the awesome format.

### Subcategories

Within each category, repos are grouped by the section heading (`##`/`###`/`####`) they appeared under in the source README. Generic sections (`Contents`, `License`, `Contributing`, `Footnotes`) are stripped. Repos that appear before any heading land in `General`.

## Limitations

A few things worth knowing about the data:

- **GitHub Search 1000-result cap.** The Search API returns at most 1000 results per query, regardless of paging. The pipeline works around this with multiple star-range bucket queries (`50..200`, `200..350`, ..., `5000..50000`), but a list outside those buckets or whose star count straddles a boundary on a given day may be missed.
- **Discovery is name-biased.** Non-canonical discovery requires either `awesome` in the repo name or membership in the `awesome-list`/`curated-list` topics. A high-quality curated list with neither will not be found.
- **Star floor of 50.** Lists below 50 stars are filtered out of search results entirely.
- **Category-level health filter (>= 50 avg).** A list whose linked repos average below 50 health is dropped. This sometimes excludes legitimate plugin lists for niche tools where most plugins are individually small.
- **README format dependence.** The parser handles markdown links (`[name](url)`) and HTML anchors (`<a href="url">name</a>`). Lists that link via images, plain text, raw URLs in tables, or unusual markup will yield few extracted repos.
- **Badge detection is regex-based.** Image-based badge variants that diverge significantly from the standard `awesome.re/badge.svg` form may be missed, pushing an otherwise official-looking list into the non-canonical tier.
- **Renamed/transferred repos.** GraphQL doesn't follow redirects, so the pipeline does a REST fallback to recover renamed repos. Repos that have been deleted or made private since the source list was last updated are silently dropped.
- **Health score is a heuristic.** It combines stars, commit recency, license presence, PR activity, and a few other signals. A high score means "actively maintained, established project" - it is not an endorsement of code quality or security.
- **Refresh cadence.** The site rebuilds once a week. Activity that happened mid-week (a star spike, a fresh release, a new awesome list) will not appear until the next Wednesday run.
- **Built-in `GITHUB_TOKEN` quota.** CI runs use the workflow's auto-provided `GITHUB_TOKEN` (5000 REST requests/hour, 30 GraphQL requests/min). A full pipeline run usually fits, but very busy weeks may hit a transient rate limit and skip a few buckets - the next run picks them back up.

---

## Architecture

```
site/                    Static site (deployed to GitHub Pages)
  index.html             Main page
  css/
    tokens.css           Design tokens (--av-* custom properties)
    base.css             Reset, typography, body defaults
    components.css       All component styles
  js/
    app.js               Client-side search, filter, sort, render
    charts.js            Visualization charts
  data/
    index.json           Lightweight index (loaded on page load)
    repos-*.json         Repo data split by tier (lazy-loaded)
    resources-*.json     Resource links split by tier (lazy-loaded)
    repos.json           Full dataset (built by pipeline, not deployed)
    search-meta.json     Autocomplete suggestions + category keywords
    viz-data.json        Pre-computed chart aggregations

scripts/
  run_pipeline.py        Pipeline runner with save points
  fetch_data.py          Step 1 - crawl awesome lists, query GitHub API
  fetch_noncanonical.py  Step 2 - discover non-canonical awesome lists
  enrich_data.py         Step 3 - BM25F search keyword extraction
  compute_viz.py         Step 4 - pre-compute chart aggregations
  split_data.py          Step 5 - split repos.json for lazy loading
  shared.py              Shared constants and health scoring

docs/
  design-system.md       Design system specification

flake.nix                Nix dev environment
.github/
  workflows/
    update-data.yml      Weekly data fetch + Pages deploy
```

## Local Development

### Prerequisites

- [Nix](https://nixos.org/download) with flakes enabled
- A GitHub personal access token for pipeline steps 1-2 (`repo` read scope is enough)

All commands run inside the Nix dev shell, which provides Python 3.12, `gh`, `git`, and `jq`. No system-level installs required.

### 1. Clone and enter the dev shell

```sh
git clone https://github.com/stradichenko/awesome-visualizer.git
cd awesome-visualizer
nix develop
```

### 2. Browse the site locally

The repo includes pre-built sample data so the site is immediately usable:

```sh
python -m http.server -d site
# open http://localhost:8000
```

### 3. Refresh the data

Set your token once, then run the pipeline. It auto-resumes from the last save point if interrupted:

```sh
export GITHUB_TOKEN="ghp_..."
python scripts/run_pipeline.py
```

Or run individual steps:

```sh
python scripts/fetch_data.py          # Step 1 - crawl + GraphQL (needs token, ~30 min)
python scripts/fetch_noncanonical.py  # Step 2 - GitHub Search (needs token, ~30 min)
python scripts/enrich_data.py         # Step 3 - search keywords (~3 min)
python scripts/compute_viz.py         # Step 4 - chart aggregations (~1 min)
python scripts/split_data.py          # Step 5 - lazy-load split (~30 sec)
```

### 4. Lint and format

```sh
nix develop --command ruff check scripts/
nix develop --command ruff format scripts/
```

## Data Pipeline

The pipeline runs as five sequential steps, orchestrated by `scripts/run_pipeline.py`:

| Step | Script | What it does | API calls |
|------|--------|--------------|-----------|
| 1 | `fetch_data.py` | Crawl awesome lists (depth 3), batch-query GitHub GraphQL for metrics | Yes |
| 2 | `fetch_noncanonical.py` | Discover unofficial/non-canonical awesome lists via GitHub Search | Yes |
| 3 | `enrich_data.py` | Compute BM25F search keywords, autocomplete suggestions | No |
| 4 | `compute_viz.py` | Pre-compute chart aggregations (language distribution, health histogram, etc.) | No |
| 5 | `split_data.py` | Split the monolithic repos.json into tier-based files for lazy loading | No |

Steps 1-2 are the expensive ones (30-60 min total, dominated by GitHub API rate limits). Steps 3-5 are pure computation and finish in under 5 minutes.

### Save points

The pipeline runner creates save points after each step so interrupted runs resume where they left off instead of starting over:

```sh
# Run (or resume) the full pipeline
python scripts/run_pipeline.py

# Check current progress
python scripts/run_pipeline.py --status

# Force restart from step 3 (reuses step 1-2 outputs)
python scripts/run_pipeline.py --from 3

# Preview what would run
python scripts/run_pipeline.py --dry-run

# Clear all save points and start fresh
python scripts/run_pipeline.py --reset
```

`fetch_data.py` also has internal checkpoints - if it crashes mid-run, re-running it skips already-completed phases (sublist crawl, GraphQL batching, recursive discovery).

### Health score

Each repo gets a 0-100 health score based on 8 weighted factors:

- **Stars** (20 pts) - normalized by tier
- **Recent commits** (20 pts) - commits in the last 90 days
- **Freshness** (20 pts) - days since last push
- **Not archived** (10 pts)
- **License** (8 pts)
- **PR activity** (8 pts) - open PRs signal active collaboration
- **Fork engagement** (7 pts) - fork-to-star ratio
- **Description** (7 pts)

## CI/CD

The GitHub Actions workflow ([.github/workflows/update-data.yml](.github/workflows/update-data.yml)) runs:

- **Weekly** at 02:00 UTC on Wednesdays via cron
- **Manually** via `workflow_dispatch` from the Actions tab

It runs the full data pipeline inside the Nix dev shell, commits any changes under `site/data/` back to `main`, then deploys `site/` to GitHub Pages using `actions/deploy-pages`.

### One-time GitHub Pages setup

After making the repo public, enable Pages with the Actions source:

1. Repo **Settings** -> **Pages**
2. Under **Build and deployment** -> **Source**, choose **GitHub Actions**

The first scheduled run (or a manual `workflow_dispatch`) will populate the deployment.

## Design System

See [docs/design-system.md](docs/design-system.md) for the full specification. Key points:

- All values via `--av-*` CSS custom properties
- Dark-first palette
- Golden-ratio spacing scale
- BEM-like naming with `av-` prefix

## License

[MIT](LICENSE)
