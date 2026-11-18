# Awesome Visualizer -- DESIGN.md

> Drop-in design reference for AI agents. Full details in `docs/design-system.md`.

## Visual Theme & Atmosphere

Dark analytical dashboard. Developer-focused, data-dense, utilitarian.
Inspired by GitHub's dark mode and IDE aesthetics. The interface recedes --
content and metrics are the focus, not chrome. Minimal ornamentation;
clarity over personality.

- **Density**: High -- compact cards, tight spacing, small base font (14px)
- **Mood**: Calm, technical, precise
- **Philosophy**: Every pixel earns its place through information

## Color Palette

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Background | `--av-bg` | `#0d1117` | Page canvas |
| Surface 1 | `--av-surface-1` | `#161b22` | Cards, navbar |
| Surface 2 | `--av-surface-2` | `#1c2129` | Inputs, elevated panels |
| Surface 3 | `--av-surface-3` | `#21262d` | Popovers, modals |
| Border | `--av-border` | `#30363d` | Default borders |
| Border emphasis | `--av-border-emphasis` | `#484f58` | Hover borders |
| Primary text | `--av-text` | `#e6edf3` | Body copy |
| Secondary text | `--av-text-secondary` | `#8b949e` | Labels, muted |
| Tertiary text | `--av-text-tertiary` | `#656d76` | Disabled, timestamps |
| Accent | `--av-primary` | `#6c63ff` | Links, active states |
| Accent hover | `--av-primary-emphasis` | `#8b83ff` | Hover accent |
| Success | `--av-success` | `#3fb950` | Health 80-100 |
| Info | `--av-info` | `#58a6ff` | Health 60-79 |
| Warning | `--av-warning` | `#d29922` | Health 40-59 |
| Danger | `--av-danger` | `#f85149` | Health 0-39 |

All colors are defined as `--av-*` CSS custom properties in `site/css/tokens.css`.
Semantic colors each have a `-muted` variant at ~15% opacity for backgrounds.

## Typography

- **Sans**: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- **Mono**: `ui-monospace, "SFMono-Regular", "SF Mono", Menlo, Consolas, monospace`
- **Base size**: 0.875rem (14px)
- **Scale**: xs 0.75rem, sm 0.8125rem, base 0.875rem, md 1rem, lg 1.125rem, xl 1.375rem, 2xl 1.75rem
- **Weights**: 400 (normal), 500 (medium), 600 (semibold), 700 (bold)
- **Line heights**: 1.25 (tight/headings), 1.5 (base/body), 1.75 (loose)

## Spacing

Golden-ratio scale using `rem`:

| Token | Value |
|-------|-------|
| `--av-size-3xs` | 0.25rem |
| `--av-size-2xs` | 0.375rem |
| `--av-size-xs` | 0.5rem |
| `--av-size-sm` | 0.75rem |
| `--av-size-md` | 1rem |
| `--av-size-lg` | 1.272rem |
| `--av-size-xl` | 1.618rem |
| `--av-size-2xl` | 2.618rem |
| `--av-size-3xl` | 4.236rem |

## Layout

- Max content width: 1400px, centered with auto margins
- Card grid: `auto-fill, minmax(320px, 1fr)`
- Stats: 4-column grid (desktop), 2-column (tablet), 1-column (mobile)
- Breakpoints: 768px (tablet), 480px (compact)

## Depth & Elevation

| Level | Surface | Shadow | Used for |
|-------|---------|--------|----------|
| 0 | `--av-bg` | none | Page background |
| 1 | `--av-surface-1` | none | Cards, navbar, controls bar |
| 2 | `--av-surface-2` | `--av-shadow-sm` | Inputs, table headers, hover states |
| 3 | `--av-surface-3` | `--av-shadow-md` | Autocomplete, dropdowns |
| Overlay | -- | `--av-shadow-lg` | Modals, popovers |

Higher elevation = lighter surface + stronger shadow.

## Component Patterns

- **Cards** (`av-card`): Surface-1, 1px border, radius-md. Hover lifts border emphasis + shadow-sm.
- **Buttons** (`av-btn`): Surface-2, 1px border. `--primary` variant uses accent bg. `aria-pressed` for toggles.
- **Inputs** (`av-input`, `av-select`): Surface-2, 1px border. Focus shows primary ring.
- **Badges** (`av-badge`): Pill shape, primary-muted bg. `--archived` uses danger colors.
- **Health bars** (`av-health`): Data-driven via `--health-pct` and `--health-color` custom properties.
- **Tables** (`av-table`): Collapsed borders, sticky surface-2 header, row hover.

## Do's and Don'ts

**Do:**
- Reference `--av-*` tokens for every visual value
- Use semantic HTML (`<article>`, `<section>`, `<nav>`, `<button>`)
- Use `data-ref` / `data-action` for JS hooks
- Use CSS transitions for interactivity (no JS animation libraries)
- Use inline SVG for icons

**Don't:**
- Hardcode hex colors, pixel sizes, or font stacks
- Add external CDN links or JS dependencies
- Use `<div onclick>` -- use `<button>` with `data-action`
- Write inline `style=""` (exception: CSS custom property injection like `--lang-color`)
- Use IDs for styling -- use `av-` prefixed classes
