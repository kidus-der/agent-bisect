# Third-party sources in `web/`

Everything below is either an npm dependency or source copied in through the shadcn CLI.
Nothing is loaded from a CDN at runtime: fonts and scripts are bundled, the dashboard works offline.

## Vendored source (copied into the repo)

| What                                                                                                                                                                                                                                   | Where                                                          | Author | Licence                                                                    | Source                                                                            |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------ | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Bklit UI charts: `area-chart`, `bar-chart`, `line-chart`, `live-line-chart`, `heatmap-chart`, `gauge-chart`, `ring-chart`, `radar-chart`, `scatter-chart`, `funnel-chart`, `sankey-chart` (+ their shared files and `shimmering-text`) | `src/components/charts/`, `src/components/shimmering-text.tsx` | bklit  | MIT ("Chart components (`packages/ui`, shadcn registry) are MIT licensed") | https://github.com/bklit/bklit-ui · registry `https://ui.bklit.com/r/{name}.json` |

Installed with `npx shadcn@latest add @bklit/<slug>`. Local changes to vendored files:

- `charts/chart-loading-label.tsx`: import path `../components/shimmering-text` → `@/components/shimmering-text` (the registry path did not resolve).
- The `@theme` lines the registry appended to `index.css` were discarded (they referenced `var(----chart-*)`, four dashes). Every `--chart-*` variable is now generated from `src/design/tokens.ts` by `src/design/tokens-css.ts`.
- `charts/line-chart.tsx`, `charts/area-chart.tsx`: the reveal `clipPath` id was hard-coded (`chart-grow-clip` / `chart-area-grow-clip`), so two line charts (or two area charts) on one page shared a single clip and the second never revealed. Both now derive the id from `useId()`, with colons stripped because it is referenced through `url(#...)` — the same convention `charts/dash-tail-stroke.tsx` already uses.
- `charts/sankey/sankey-chart.tsx`: added an optional `minNodeHeight`. A node holding 3 of 86 units lays out a few pixels tall and can be neither read nor hovered; only the node rect grows, so the ribbons keep their proportional endpoints. Defaults to 0, so unchanged for every other caller.
- `charts/ring-context.tsx`: the ring's unfilled track was `var(--border)`, a hairline token at roughly 1.2:1 on white. The unfilled arc is what shows the remaining portion, so it is a data mark and needs 3:1 (WCAG 1.4.11); it now uses from-tape slate, which clears 3:1 in both themes.
- `charts/live-line.tsx`: the live value badge hard-coded `fontFamily="SF Mono, Menlo, Monaco, monospace"` and a 6px radius, so it read as a foreign face next to every other numeral. It now uses `var(--font-mono)` with tabular numerals, the 4px step radius and a `line-strong` hairline.

shadcn/ui itself (MIT, https://ui.shadcn.com) is used as CLI + `shadcn/tailwind.css` only; its generated `ui/` components were removed because the primitives here are built directly on Radix.

## npm dependencies that ship in the bundle

| Package                                                                                                         | Licence      |
| --------------------------------------------------------------------------------------------------------------- | ------------ |
| react, react-dom                                                                                                | MIT          |
| @tanstack/react-router, @tanstack/react-query, @tanstack/react-virtual                                          | MIT          |
| motion                                                                                                          | MIT          |
| cmdk                                                                                                            | MIT          |
| radix-ui                                                                                                        | MIT          |
| lucide-react                                                                                                    | ISC          |
| tailwindcss, @tailwindcss/vite, tw-animate-css, tailwind-merge, clsx, class-variance-authority                  | MIT          |
| @visx/* (curve, event, gradient, grid, group, heatmap, pattern, responsive, sankey, scale, shape)               | MIT          |
| d3-array, d3-scale, d3-shape                                                                                    | ISC          |
| d3-sankey                                                                                                       | BSD-3-Clause |
| @number-flow/react, react-use-measure                                                                           | MIT          |
| @fontsource-variable/geist, @fontsource-variable/geist-mono (Geist and Geist Mono by Vercel, self-hosted woff2) | OFL-1.1      |

## 21st.dev candidates from `docs/design/direction.md` §6

None adopted in round 0. None of their source was copied, so no 21st.dev licence applies to this repo.

| Candidate                 | Author        | URL                                                                   | Decision              | Why                                                                                                                                                                                                                                                                                  |
| ------------------------- | ------------- | --------------------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Basic Number Ticker       | danielpetho   | `21st.dev/@danielpetho/components/basic-number-ticker`                | Not adopted           | `useNumberTicker` in `src/design/motion.ts` is ~30 lines on Motion's `animate()` with our `ticker` spring and writes to a ref (no re-render); importing a component to then replace its easing, font and markup would have kept nothing of it. Licence was never verified at source. |
| Command Palette           | jatin-yadav05 | `21st.dev/community/components/jatin-yadav05/command-palette/default` | Not adopted           | Community component with no licence stated in research; the palette is built on `cmdk` (MIT) + Radix Dialog directly, in the Raycast list + detail layout.                                                                                                                           |
| Dot Grid (Shader Builder) | paper-design  | `21st.dev/@paper-design/components/dot-grid`                          | Not adopted (round 0) | Apache-2.0 as stated, but it is a WebGL shader; the blueprint texture here is a static CSS `radial-gradient` (`blueprint-dots` utility): zero JS, no GPU cost on dense views. Revisit only for the Overview hero.                                                                    |
| Sortable Table            | ddoemonn      | `21st.dev/@ddoemonn/components/sortable-table`                        | Not adopted           | Licence unclear ("community component"); `DataTable` needs virtualization and custom cell renderers, so it is built on `@tanstack/react-virtual` (MIT).                                                                                                                              |
