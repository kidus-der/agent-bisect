# Bisect dashboard (`web/`)

React 19 + Vite + TypeScript strict + Tailwind v4. Served in production by `bisect serve`
from `agent_bisect/server/static/` (the build output; not committed by default).

```
npm install
npm run dev          # http://127.0.0.1:5173, /api proxied to http://127.0.0.1:8484
npm run build        # tsc -b && vite build -> ../agent_bisect/server/static/
npm run typecheck
npm run lint         # eslint + prettier --check
npm test             # vitest (tokens contrast, primitives, shell, apiFetch)
npm run e2e          # playwright + axe (own dev server on :5183, API mocked)
npm run screenshots  # docs/screenshots/round0/*.png
```

- `src/design/tokens.ts` is the single source of truth. `npm run tokens` (also run by
  `predev`, `prebuild`, `pretest`) writes `src/design/tokens.generated.css`: the CSS variables
  for both themes, the shadcn aliases, every Bklit `--chart-*` variable and the Tailwind
  `@theme` mapping. A unit test fails if the file is stale or any pair drops under WCAG AA.
- Theme is `data-theme` on `<html>`, set before paint by the inline script in `index.html`
  (localStorage `bisect.theme`, else `prefers-color-scheme`).
- `src/design/motion.ts`: the five named springs; every helper becomes an instant state
  change under `prefers-reduced-motion`.
- `/gallery` is the kitchen sink: every primitive, state and chart in the current theme.
- Third-party sources and licences: `THIRD_PARTY.md`.
