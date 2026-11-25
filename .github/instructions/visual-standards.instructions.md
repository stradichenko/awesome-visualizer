---
description: "Use when creating, editing, or reviewing CSS files, visual components, styling, or any front-end visual element."
applyTo: "site/**"
---
# Visual Standards for Awesome Visualizer

All visual work follows `docs/design-system.md`.

## Quick Rules

1. **Tokens only** -- every color, spacing, border-radius, shadow, font-size,
   and font-weight must use a `--av-*` custom property from `site/css/tokens.css`.
   Never write raw hex, rgb, or px values (except `1px` for borders).

2. **Class prefix** -- all custom classes start with `av-`. Use BEM-like naming:
   `av-card`, `av-card-header`, `av-card--elevated`, `av-btn--primary`.
   State classes: `is-active`, `is-disabled`, `is-loading`.

3. **No new dependencies** -- no CDN links, no icon font CDNs, no JS libraries.
   Animations use CSS `transition` or `@keyframes`.

4. **No inline styles** -- write CSS in appropriate files under `site/css/`.
   Exception: CSS custom property injection for data-driven values
   (e.g., `style="--lang-color: #f1e05a"`).

5. **Semantic color tokens** -- use `--av-success`, `--av-warning`, `--av-danger`,
   etc. for status-dependent styling. Each has a `-muted` variant for backgrounds.

6. **Dark-first** -- default theme is dark. Components must reference tokens
   so a future light theme works by redefining `:root` values only.

7. **Responsive** -- components must not break below 768px. Use `flex-wrap`,
   `clamp()`, `minmax()`, CSS Grid, or media queries.

8. **Accessible** -- contrast ratio >= 4.5:1 for text, >= 3:1 for interactive
   elements. Use semantic HTML and `aria-*`.

## Health Score Colors

| Score   | Token            | Meaning |
|---------|------------------|---------|
| 80-100  | `--av-success`   | Great   |
| 60-79   | `--av-info`      | Good    |
| 40-59   | `--av-warning`   | Fair    |
| 0-39    | `--av-danger`    | Poor    |

## Spacing Scale

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
