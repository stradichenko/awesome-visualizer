---
description: "Use when creating or editing HTML files -- covers semantic structure, accessibility, form labels, IDs, data attributes, and event handlers."
applyTo: "site/**/*.html"
---
# HTML Conventions for Awesome Visualizer

All markup must follow `docs/design-system.md`.

## ID Naming

- **kebab-case only**: `search-input`, `filter-category`.
- **Include a hyphen** to avoid `window` global collisions.
- **Scope IDs** with a feature prefix: `search-`, `filter-`, `sort-`, `stat-`.
- **Minimize IDs** -- prefer `data-*` for JS hooks, `class` for styling.

## Semantic Structure

- One `<main>` per page wrapping primary content.
- `<section>` for thematic groups with a heading.
- `<article>` for self-contained content (e.g., repo cards).
- `<nav>` with `aria-label` when multiple navs exist.
- `<div>` only when no semantic element applies.

## Accessibility

- `aria-pressed` on toggle buttons (view-grid, view-table).
- `aria-live="polite"` on dynamically-updated containers.
- `aria-label` on icon-only buttons.
- `alt` on every `<img>` (empty for decorative).
- `scope="col"` / `scope="row"` on table header cells.
- `<caption>` on data tables (`.av-sr-only` if hidden).

## Prohibited Patterns

| Pattern                    | Use Instead                                |
|----------------------------|--------------------------------------------|
| `<style>` block in HTML    | External CSS file in `site/css/`           |
| `style=""` inline (raw)    | CSS class or `--av-*` custom property      |
| `onclick="..."` handler    | `data-action` + delegated JS listener      |
| `<div onclick>` as button  | `<button>` with `data-action`              |
| Hardcoded hex color        | `var(--av-*)` token                        |

Exception: `style="--lang-color: #hex"` for CSS custom property injection is allowed.

## data-* Attributes

- `data-ref="name"` -- DOM element references for JS.
- `data-action="verb"` -- Action buttons for delegated listeners.
- `data-page="n"` -- Pagination page targets.

## Buttons vs Links

- `<a>` for navigation (goes somewhere).
- `<button>` for actions (does something).
