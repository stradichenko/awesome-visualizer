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
  data/
    repos.json           Repo data (sample for dev, fresh from CI)

scripts/
  fetch_data.py          Data pipeline (GitHub API -> repos.json)

docs/
  design-system.md       Design system specification

flake.nix                Nix dev environment
.github/
  workflows/
    update-data.yml      Daily data fetch + Pages deploy
```

## Local Development

All commands run inside the Nix dev shell.

```sh
# Enter the dev shell
nix develop

# Start a local server
python -m http.server -d site

# Fetch fresh data (requires GITHUB_TOKEN)
GITHUB_TOKEN="ghp_..." python scripts/fetch_data.py
```

The repo includes sample data in `site/data/repos.json` so the site works immediately without running the pipeline.

## Data Pipeline

`scripts/fetch_data.py` does the following:

1. Fetches the sindresorhus/awesome README via the GitHub REST API
2. Parses markdown to extract GitHub repo links grouped by category
3. Batch-queries repo metrics via the GitHub GraphQL API (40 repos per query)
4. Computes a 0-100 health score for each repo
5. Writes `site/data/repos.json`

Health score formula (4 dimensions, 25 points each):
- **Stars** -- normalized by tier (10k+ = 25)
- **Recent commits** -- commits in the last 90 days
- **Freshness** -- days since last push
- **Community** -- license, description, not archived

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
