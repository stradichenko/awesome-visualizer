# Awesome Visualizer -- Project Instructions

## Tech Stack

- Static site: HTML, CSS, vanilla JavaScript
- Data pipeline: Python 3.12+
- Build/CI: GitHub Actions (daily cron + on-push deploy)
- Hosting: GitHub Pages
- Package/environment management: Nix flake

## Nix Environment (Critical)

**Every command must run within the Nix dev shell.** No global installs.

- Enter interactively: `nix develop`
- One-shot: `nix develop --command <cmd>`
- CI uses `nix develop --command` for all steps
- The flake provides: Python 3.12 (with `requests`), `gh`, `git`, `jq`

## Code Style

- Python: `snake_case` for variables and functions. Follow patterns in `scripts/`.
- JavaScript: vanilla only. `camelCase`. No frameworks, no jQuery, no npm.
- CSS: all values via `--av-*` design tokens. See `docs/design-system.md`.
- No em-dashes. Use `-` instead.
- Don't use emojis, use inline SVG icons instead.
- Avoid hard wrapping lines. Use line breaks only for readability.
- Use `kebab-case` for CSS classes, IDs, and `data-*` attributes.

## Design System

All visual work must follow `docs/design-system.md`. Key rules:

1. Every color, spacing, radius, shadow, and font value must reference a
   `--av-*` CSS custom property from `site/css/tokens.css`.
2. No hardcoded hex colors or pixel sizes.
3. New components use the `av-` class prefix with BEM-like naming.
4. No new JavaScript dependencies for visual effects -- CSS transitions only.
5. No CDN links. Inline SVG for icons.
6. Dark-first theming -- never bake literal color values into components.

## HTML Conventions

1. IDs use **kebab-case** with a feature-prefix (`search-input`, `filter-category`).
2. Semantic HTML required: `<main>`, `<section>`, `<nav>`, `<article>`.
3. Every form input has a `<label>` with matching `for`/`id`.
4. Use `data-*` attributes for JS hooks -- `data-ref` for DOM refs,
   `data-action` for action buttons.
5. No inline `style=""` except CSS custom property injection for data-driven
   values (e.g., `style="--lang-color: #f1e05a"`).
6. `<button>` for actions, `<a>` for navigation -- no `<div onclick>`.
7. Icon-only buttons need `aria-label`.

## File Organization

```
site/                    # Static site (deployed to GitHub Pages)
  index.html             # Main page
  css/
    tokens.css           # Design tokens (single source of truth)
    base.css             # Reset, typography, body defaults
    components.css       # All component styles
  js/
    app.js               # Client-side search, filter, sort, render
  data/
    repos.json           # Repo data (sample for dev, fresh from CI)
scripts/
  fetch_data.py          # Data pipeline (GitHub API -> repos.json)
flake.nix                # Nix dev environment
.github/
  workflows/
    update-data.yml      # Daily data fetch + Pages deploy
```
