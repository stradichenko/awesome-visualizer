# Awesome Visualizer: Design System

A CSS-only, zero-JS-dependency visual system for Awesome Visualizer.
Dark-first, token-driven, responsive. No frameworks, no build step.

---

## Principles

1. **Token-only:** Every color, spacing, radius, shadow, and font value
   comes from `--av-*` custom properties in `site/css/tokens.css`.
2. **Dark-first:** Default palette is dark. Future light theme overrides
   the same tokens on `:root`.
3. **No frameworks:** Pure CSS custom properties + vanilla CSS.
4. **Relative units:** `rem` for layout, `em` for component-local spacing.
   Reserve `px` only for borders and sub-pixel corrections.
5. **Accessible:** Contrast >= 4.5:1 for text, >= 3:1 for interactive
   elements. Semantic HTML always.

---

## Visual Theme & Atmosphere

Dark analytical dashboard. Developer-focused, data-dense, utilitarian.
Inspired by GitHub's dark mode and IDE aesthetics. The interface recedes --
content and metrics are the focus, not chrome. Minimal ornamentation;
clarity over personality.

- **Density**: High; compact cards, tight spacing, small base font (14px)
- **Mood**: Calm, technical, precise
- **Philosophy**: Every pixel earns its place through information

---

## File Layout

```
site/
  css/
    tokens.css       # Design tokens (single source of truth)
    base.css         # Reset, typography, scrollbar, selections
    components.css   # All component styles
  js/
    app.js           # Client-side logic
  index.html         # Main page
```

---

## Design Tokens

Defined on `:root` in `tokens.css`. ONLY source of truth for visual values.

### Spacing Scale (Golden Ratio)

| Token           | Value    |
|-----------------|----------|
| `--av-size-3xs` | 0.25rem  |
| `--av-size-2xs` | 0.375rem |
| `--av-size-xs`  | 0.5rem   |
| `--av-size-sm`  | 0.75rem  |
| `--av-size-md`  | 1rem     |
| `--av-size-lg`  | 1.272rem |
| `--av-size-xl`  | 1.618rem |
| `--av-size-2xl` | 2.618rem |
| `--av-size-3xl` | 4.236rem |

### Surfaces

| Token            | Value     | Usage               |
|------------------|-----------|---------------------|
| `--av-bg`        | `#0d1117` | Page background     |
| `--av-surface-1` | `#161b22` | Cards, navbar       |
| `--av-surface-2` | `#1c2129` | Elevated elements   |
| `--av-surface-3` | `#21262d` | Popovers, modals    |

### Borders

| Token                  | Value     |
|------------------------|-----------|
| `--av-border`          | `#30363d` |
| `--av-border-emphasis` | `#484f58` |

### Text

| Token                   | Value     | Usage            |
|-------------------------|-----------|------------------|
| `--av-text`             | `#e6edf3` | Primary text     |
| `--av-text-secondary`   | `#8b949e` | Labels, muted    |
| `--av-text-tertiary`    | `#656d76` | Disabled         |
| `--av-text-on-emphasis` | `#ffffff` | On colored bg    |

### Accent

| Token                   | Value                     |
|-------------------------|---------------------------|
| `--av-primary`          | `#6c63ff`                 |
| `--av-primary-emphasis` | `#8b83ff`                 |
| `--av-primary-muted`    | `rgba(108,99,255,0.15)`   |

### Semantic

| Token           | Value     | Meaning          |
|-----------------|-----------|------------------|
| `--av-success`  | `#3fb950` | Healthy / great  |
| `--av-warning`  | `#d29922` | Fair / stale     |
| `--av-danger`   | `#f85149` | Poor / dead      |
| `--av-info`     | `#58a6ff` | Good / active    |
| `--av-neutral`  | `#8b949e` | Default          |

Each has a `-muted` variant at ~15% opacity for backgrounds.

### Typography

| Token                        | Value                |
|------------------------------|----------------------|
| `--av-font-sans`             | system-ui stack      |
| `--av-font-mono`             | ui-monospace stack   |
| `--av-font-size-xs`          | 0.75rem              |
| `--av-font-size-sm`          | 0.8125rem            |
| `--av-font-size-base`        | 0.875rem             |
| `--av-font-size-md`          | 1rem                 |
| `--av-font-size-lg`          | 1.125rem             |
| `--av-font-size-xl`          | 1.375rem             |
| `--av-font-size-2xl`         | 1.75rem              |
| `--av-font-weight-normal`    | 400                  |
| `--av-font-weight-medium`    | 500                  |
| `--av-font-weight-semibold`  | 600                  |
| `--av-font-weight-bold`      | 700                  |

### Layout

| Token                  | Value                          |
|------------------------|--------------------------------|
| `--av-radius-sm`       | 4px                            |
| `--av-radius-md`       | 6px                            |
| `--av-radius-lg`       | 8px                            |
| `--av-radius-pill`     | 50rem                          |
| `--av-shadow-sm`       | 0 1px 2px rgba(0,0,0,0.3)     |
| `--av-shadow-md`       | 0 4px 12px rgba(0,0,0,0.4)    |
| `--av-shadow-lg`       | 0 8px 24px rgba(0,0,0,0.5)    |
| `--av-transition-fast` | 120ms ease                     |
| `--av-transition-base` | 200ms ease                     |
| `--av-content-max`     | 1400px                         |

---

## Component Catalogue

### Navbar (`.av-navbar`)

- Sticky top, `var(--av-surface-1)` background
- Border bottom: `1px solid var(--av-border)`

### Stat Cards (`.av-stat`)

- 4-column grid at desktop, 2 at tablet, 1 at mobile
- Number in `var(--av-primary)`, label in `var(--av-text-secondary)`

### Cards (`.av-card`)

```html
<article class="av-card">
  <header class="av-card-header">
    <span class="av-lang-dot" style="--lang-color: #f1e05a"></span>
    <a href="..." class="av-card-title">repo-name</a>
    <span class="av-card-owner">owner</span>
  </header>
  <p class="av-card-desc">Description text</p>
  <footer class="av-card-footer">
    <div class="av-card-metrics">...</div>
    <div class="av-health">...</div>
    <div class="av-card-meta">...</div>
  </footer>
</article>
```

- Background: `var(--av-surface-1)`
- Border: `1px solid var(--av-border)`
- Hover: border emphasis + small shadow
- Grid: `auto-fill, minmax(320px, 1fr)`

### Health Bar (`.av-health`)

Uses CSS custom properties for data-driven styling:
- `--health-pct`: width percentage
- `--health-color`: bar and score color

Score thresholds:
- 80-100: `var(--av-success)` (great)
- 60-79: `var(--av-info)` (good)
- 40-59: `var(--av-warning)` (fair)
- 0-39: `var(--av-danger)` (poor)

### Badges (`.av-badge`)

- Pill shape, `var(--av-primary-muted)` background
- `--archived` variant uses danger colors

### Tables (`.av-table`)

- Full width, collapsed borders
- Sticky header with `var(--av-surface-2)` background
- Row hover: `var(--av-surface-2)`
- Horizontal scroll wrapper for mobile

### Buttons (`.av-btn`)

- Default: surface-2 background, border
- `--icon`: square, equal padding
- `--primary`: primary background, white text
- `[aria-pressed="true"]`: highlighted active state

### Pagination (`.av-pagination`)

- Centered, gap between buttons
- `.is-active`: primary background

---

## Naming Conventions

### CSS Classes

- **Prefix**: `av-` for all custom classes
- **BEM-like**: `av-card`, `av-card-header`, `av-card--elevated`
- **State**: `is-active`, `is-disabled`, `is-loading` (no prefix)
- **Tokens**: `--av-{category}-{name}`

### HTML IDs

- **kebab-case** with feature prefix: `search-input`, `filter-category`
- Minimize ID usage; prefer `data-*` for JS hooks

### data-* Attributes

- `data-ref="name"`: DOM element references for JS
- `data-action="verb"`: Action buttons for delegated listeners
- `data-page="n"`: Pagination targets

---

## Depth & Elevation

Surfaces get lighter and shadows get stronger as elements rise.

| Level | Surface token | Shadow token | Typical usage |
|-------|---------------|--------------|---------------|
| 0 (base) | `--av-bg` | none | Page background |
| 1 | `--av-surface-1` | none | Cards, navbar, controls bar |
| 2 | `--av-surface-2` | `--av-shadow-sm` | Inputs, table headers, hover states |
| 3 | `--av-surface-3` | `--av-shadow-md` | Autocomplete dropdown, popovers |
| Overlay | (none) | `--av-shadow-lg` | Modals, full-screen overlays |

Rule: never skip levels. A popover (level 3) should not sit directly on the
page background (level 0) without context.

---

## Responsive Breakpoints

| Name | Max-width | Key changes |
|---------|-----------|----------------------------------------------|
| Desktop | (none) | 4-col stats, multi-col card grid, full navbar |
| Tablet | 768px | 2-col stats, 1-col cards, stacked controls |
| Compact | 480px | 1-col stats |

Design targets:
- Touch targets >= 44px on tablet and below
- Card grid collapses to single column at 768px
- Navbar padding and font size reduce at 768px
- Controls bar stacks vertically at 768px
- Stats grid goes to 1-column at 480px

---

## Do's and Don'ts

**Do:**

1. Reference `--av-*` tokens for every color, spacing, radius, and shadow
2. Use semantic HTML: `<article>`, `<section>`, `<nav>`, `<button>`
3. Use `data-ref` / `data-action` attributes for JS hooks
4. Use CSS transitions (`--av-transition-fast`, `--av-transition-base`)
5. Use inline SVG for all icons
6. Test at all three breakpoints before shipping

**Don't:**

1. Hardcode hex colors, pixel sizes, or font stacks in component CSS
2. Add external CDN links, icon fonts, or JS animation libraries
3. Use `<div onclick>`; always use `<button>` with `data-action`
4. Write inline `style=""` (exception: CSS custom property injection)
5. Assign IDs for styling; use `av-`-prefixed classes
6. Skip elevation levels (e.g., popover directly on page background)

---

## Rules for New Components

1. Token-only: no magic numbers
2. No JS for visuals: CSS transitions and keyframes only
3. No CDN dependencies: inline SVG for icons
4. Responsive: must not break below 768px
5. Accessible: semantic HTML, aria-* where needed, 4.5:1 contrast
6. Dark-first: reference tokens, never hardcode colors
