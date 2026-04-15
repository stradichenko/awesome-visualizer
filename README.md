<p align="center">
  <img src="site/logo.svg" alt="Awesome Visualizer logo" width="200">
</p>

# Awesome Visualizer

A data-driven explorer for the [sindresorhus/awesome](https://github.com/sindresorhus/awesome) ecosystem. Browse, search, filter, and compare awesome list repositories with rich metrics -- stars, forks, commit activity, health scores -- all on a fast static site hosted on GitHub Pages.

## Features

- Filterable card grid and table views
- Full-text client-side search across repo names, descriptions, and topics
- Filter by category, language, and health score
- Sort by stars, health, recent activity, commits, or name
- Health score (0-100) combining stars, commit freshness, activity, and community signals
- Daily data refresh via GitHub Actions
- Dark-first design, fully responsive, no external dependencies

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

All commands run inside the Nix dev shell.

```sh
# Enter the dev shell
nix develop

# Start a local server
python -m http.server -d site

# Run the full pipeline (resumes from last save point)
GITHUB_TOKEN="ghp_..." python scripts/run_pipeline.py

# Or run individual steps
GITHUB_TOKEN="ghp_..." python scripts/fetch_data.py
python scripts/enrich_data.py
python scripts/compute_viz.py
python scripts/split_data.py
```

The repo includes sample data in `site/data/` so the site works immediately without running the pipeline.

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

The GitHub Actions workflow (`.github/workflows/update-data.yml`) runs:

- **Daily** at 02:00 UTC via cron
- **On push** to `main`
- **Manually** via workflow_dispatch

It uses the Nix environment to run the data pipeline, then deploys `site/` to GitHub Pages.

## Design System

See [docs/design-system.md](docs/design-system.md) for the full specification. Key points:

- All values via `--av-*` CSS custom properties
- Dark-first palette
- Golden-ratio spacing scale
- BEM-like naming with `av-` prefix

## License

MIT
