# Bisect — Dashboard Design Direction

Research for `bisect serve`, the local web dashboard for counterfactual replay of LLM
agent failures. Stack is fixed (React 19 + Vite + TS strict + Tailwind v4 + shadcn/ui,
Bklit UI charts, visx/d3 for the forest plot and step timeline, Motion for React,
TanStack Query/Router, cmdk, Geist/Geist Mono). This document sets the visual and
motion direction other agents will implement against.

## 1. References

All sites below were opened in a real browser session and screenshotted at
1489×812, except the two galleries, which were browsed and filtered live.

1. **Warp** — https://warp.dev.
   *Layout*: light theme, dotted-graph-paper canvas behind a floating dark
   "factory.yaml" panel with a `LIVE` badge and a metrics footer
   (`112 tasks · 1 agents active · 1,422 PRs shipped`); numbered feature list.
   *Type*: monospace nav/labels/metrics, plain grotesk headlines.
   *Motion*: sticky nav flips to violet on scroll; nav items carry keyboard-shortcut
   glyphs (`[S] SDLC`).
   *Colour*: acid yellow-green + violet on near-white, black product chrome.
   Take: live badge + monospace metrics strip → our Live footer / Runs table header.

2. **Raycast** — https://raycast.com.
   *Layout*: near-black hero, huge centred headline. Below the fold, a macOS chrome
   mockup frames the real product: a floating command panel — top filter bar, left
   result list with icons, right detail/preview pane.
   *Type*: bold grotesk display, small mono metadata.
   *Motion*: grainy red diagonal glow behind the hero, not a smooth gradient.
   *Colour*: monochrome dark UI, one red accent (`#FF6363`).
   Take: reference for our ⌘K palette's list+detail split and single-signal accent use.

3. **Bklit UI** — https://bklit.com (our chart vendor).
   *Layout*: true-black hero on a blueprint grid with dashed hatched corner marks
   (cross-hair "registration" ticks) — a technical-drawing motif. Dark bento grid of
   chart cards with hairline borders, not shadows; a ring chart animates in with a
   centred `100 / Total` label, a bar chart builds in below it.
   *Type*: tight grotesk headline, monospace all-caps labels with a trailing
   underscore (`TRUSTED BY PEOPLE AT_`).
   *Motion*: chart marks animate in on scroll-into-view — confirms "animate in on
   first view" is native to the library.
   *Colour*: near-grayscale chart lines on black, accent reserved not default.
   Take: corner registration marks + underscored mono labels give an "instrumented"
   feel that fits a causal-testing tool.

4. **Motion (motion.dev)** — https://motion.dev (our animation library).
   *Layout*: full-bleed acid-yellow hero, animated ASCII/dot-matrix field morphing
   green→pink→purple→red, black info card overlaid (`OPEN SOURCE / MIT LICENSE`,
   version, framework-switcher tabs).
   *Type*: bold black slab-ish grotesk, monospace metadata chips.
   *Motion*: the hero background *is* the animation demo — motion as content.
   *Colour*: loud (a library flexing); we take the typography/chip pattern, not the
   palette.

5. **Supabase** — https://supabase.com.
   *Layout*: dark ground, feature bento grid where each card pairs a short
   description with a small live-feeling diagram (route list with mono tags, rotating
   3D point-cloud cube, file-type grid). One signature green used only on the hero's
   second line and primary CTA — everywhere else grayscale.
   *Type*: clean grotesk, monospace for code/route tags.
   *Motion*: cards feel alive via small looping diagrams, not page-level animation.
   Take: model for restrained single-accent discipline — validates amber-for-blame-only.

6. **Railway** — https://railway.com.
   *Layout*: full-bleed painterly illustrated cloudscape behind a dark floating
   product-chrome card ("New Project" empty state) — illustration paired with a
   literal UI screenshot in the same hero.
   *Type*: serif display headline mixed with sans body — warm, unusual for a dev tool.
   *Motion*: violet gradient CTA, glowing card edge.
   *Colour*: violet/purple on near-black chrome over a warm illustrated sky.
   Take: proof a dev-tool hero needn't be a gradient-mesh cliché; permission for an
   unexpected type pairing and a literal product screenshot as hero content.

7. **curated.design** — https://curated.design, filtered to "Development Tools"
   (`?category=development-tools`). Confirms **Superset** (superset.sh) is catalogued
   there; also surfaced **Zoah**, **Archonum**, **Oqoqo** — thumbnails were still
   lazy-loading at capture time, so these three are **UNVERIFIED**, leads only. An
   earlier text-only pass (also UNVERIFIED, not screenshotted) surfaced **WorkOS
   Atlas**, **Mintlify**, **Conductor Build** in the same category.

8. **recent.design** — https://recent.design. Shot-level gallery (individual screens
   tagged Web/Interface/Motion…, not full sites), less useful for page layout. Two
   shots worth noting: a violet-glow "New Chat" floating panel and a particle
   point-cloud sphere — both license a glowing dot-cloud as a current way to render
   abstract multi-point data, taken for the dot-matrix and forest-plot entrance (§7).

## 2. Moodboard

**Density.** Two families: monospace-dense "instrument panel" sites (Warp, Bklit,
Motion — metrics footers, live badges, version chips) vs. airy near-empty hero sites
(Raycast, Railway) that densify only at the product screenshot. Bisect should default
dense throughout, but keep Raycast's wide calm margin around the single *focal*
element per view so density doesn't read as clutter.

**Grids vs. borders vs. shadows.** None of the six primary references lean on drop
shadows for hierarchy. Warp/Bklit use a dot/blueprint grid as page texture;
Bklit/Supabase use 1px hairline card borders at low contrast, doing the separation
work shadows would otherwise do. Elevation (Railway's floating card, Raycast's
palette) comes from glow/backdrop-blur plus a lighter fill, not a shadow. **Decision:
border + fill-step elevation, no box-shadows above `elevated`; a soft glow only on the
single most-important floating element per view.**

**Numerals.** Warp and Bklit foreground raw numbers as first-class content
(`112 tasks`, `100 / Total`) in tight monospace/tabular sans, large, with a small
caption underneath — exactly the KPI-ticker/blame-number pattern Bisect needs.

**How they show code and structure.** Warp's YAML panel, Supabase's route-tag list,
and Bklit's underscored mono labels all present real machine syntax as UI chrome, not
prose. Bisect should do the same with step IDs, DB keys, and intervention names —
literal monospace tokens in pill/chip framing.

**Accent discipline.** Supabase is the clearest lesson: one accent colour on exactly
two things (a headline word, a CTA), everywhere else grayscale. Bisect's five-way
semantic palette is already more colour than any reference site spends casually — the
lesson is to spend it as deliberately: blame amber only ever means blame.

**Motion character.** Every reference animates as *content demonstration* (Bklit's
charts building in, Motion's hero-as-demo, Supabase's looping diagrams), not
decoration on top of static content. Rewind, blame-reveal, and the forest plot should
read the same way — the animation *is* the information.

**Corner/registration marks.** Bklit's hairline corner cross-ticks and Warp's dotted
canvas both signal "instrumented, measured" without saying so — a strong metaphorical
fit for a causal-testing tool. Adopted in restrained form (§3).

## 3. Direction statement

Bisect's dashboard should feel like a **measurement instrument for causality**, not a
generic analytics SaaS: the organising visual metaphor is *the tape* — a literal
horizontal sequence of recorded steps that can be scrubbed, rewound, and re-run, shown
with the same confidence a lab instrument shows a signal trace — paired with a
blueprint/graph-paper texture and hairline instrumentation marks that make every
screen feel measured rather than merely reported. Numbers are the hero: KPI tickers,
blame scores, and confidence intervals get monospace tabular treatment and generous
size, because the product's entire value is a trustworthy number with an interval
around it. Colour is spent like a signal, not a decoration.

**Principles:**
1. **The tape is the spine.** Every run-scoped view keeps the step timeline visually
   present and horizontally continuous, even as panels below it change — the one
   element users should always find at a glance.
2. **Amber is reserved for blame, absolutely.** No button, focus ring, or decorative
   accent uses the amber→coral gradient. Amber always means "this step is the cause."
3. **Numbers over narrative.** Prefer a tabular-numeral stat with a caption to a
   sentence of prose wherever a number can carry the meaning (mirrors Warp/Bklit's
   metrics-footer pattern).
4. **Instrumented, not decorated.** Hairline borders, blueprint canvas texture, and
   underscored mono labels (`RECALL@M_`) stand in for Bklit's corner-mark
   "measurement equipment" feeling — sparingly, on headers/canvases, never in tables.
5. **One glow at a time.** Only the single most-important floating element per view
   (palette, playhead, a just-revealed blame card) gets a soft glow; else flat fill.
6. **Replay is data, not chrome.** Animations representing a real event must be
   accurate to its timing/values — never a generic flourish standing in for computation.
7. **From-tape is the quiet baseline.** Slate is the "nothing happened here" state
   every other semantic colour reads as an event against.

## 4. Tokens spec

Contrast ratios computed with a WCAG relative-luminance script
(`(L1+0.05)/(L2+0.05)`), not eyeballed.

### Neutrals

| Token | Dark | Light |
|---|---|---|
| ground | `#0B0D12` | `#F5F6F8` |
| surface | `#12151C` | `#FFFFFF` |
| elevated | `#191D27` | `#FBFBFD` |
| line | `#242A37` | `#DEE2E9` |
| text primary | `#E8EBF2` | `#12141B` |
| muted | `#8A93A6` | `#5B6478` |
| focus ring | `#4CC9F0` (measurement cyan, 2px, 2px offset) | same |

Text-on-background, dark: primary 16.3:1 (ground) / 15.3:1 (surface) / 14.1:1
(elevated); muted 6.3 / 5.9 / 5.5:1 — all comfortably clear AA (4.5:1) even for muted.
Light theme: primary 17.0 / 18.4 / 17.8:1; muted 5.5 / 5.9 / 5.7:1 — same margin.

### Semantic roles

Dark theme keeps the brief's values as-is; every one clears AA by a wide margin
(worst case **from-tape at 3.08:1 on surface** — used only for non-text marks:
tape-step fill, borders, muted dots, so it's held to WCAG 1.4.11's 3:1
non-text/UI-component minimum, which it clears; a from-tape *label*, if ever needed,
pairs an icon with the neutral `muted` text token instead of colouring the text).

Light theme needed adjustment: full-saturation hues don't clear 4.5:1 against a light
ground (e.g. amber at 2.0:1 on white). Hue preserved; lightness pulled down until each
clears 4.5:1 against `ground` (the harder background, slightly darker than white).

| Role | Dark hex | Dark on ground / surface | Light hex | Light on ground / surface |
|---|---|---|---|---|
| Blame amber | `#F5A524` | 9.52 / 8.95 | `#9C5B08` | 4.96 / 5.37 |
| Blame coral | `#F7625B` | 6.34 / 5.96 | `#C93838` | 4.73 / 5.11 |
| Measurement cyan | `#4CC9F0` | 10.11 / 9.50 | `#0B7398` | 4.95 / 5.36 |
| Judge violet | `#A78BFA` | 7.14 / 6.71 | `#7250D6` | 5.07 / 5.48 |
| Pass | `#3DD68C` | 10.36 / 9.74 | `#0F7A4C` | 4.97 / 5.37 |
| Fail | `#F25F5C` | 6.08 / 5.71 | `#C63432` | 4.93 / 5.33 |
| From-tape (slate) | `#5B6478` | 3.28 / 3.08 | `#5B6478` (unchanged) | 5.49 / 5.93 |

Worst dark ratio: **from-tape at 3.08:1** (non-text use only). Worst light ratio:
**blame coral at 4.73:1** (clears AA text). The blame gradient (amber→coral) is a
fill, not text — the blame *number* renders as `text primary`/white with a 1px dark
outline or a solid-amber chip behind it, never read directly against the gradient.

Chart series order (Bklit charts, treated/control/multi-series contexts): measurement
cyan → judge violet → pass → fail → from-tape → blame amber (blame amber last/reserved,
never assigned to an arbitrary series — see principle 2).

### Type

Geist (UI, headings, body) / Geist Mono (all numerals, code, IDs, step tokens, labels
with a trailing underscore). Tabular numerals (`font-variant-numeric: tabular-nums`)
on every KPI, ticker, table numeric column, and CI bound — non-negotiable, this is what
makes number tickers and table columns not jitter.

| Scale | Size / Line | Weight | Use |
|---|---|---|---|
| display | 44/48, -0.02em | 650 | Overview hero result headline |
| h1 | 28/34 | 600 | Page title |
| h2 | 20/28 | 600 | Section header |
| h3 | 15/22 | 600 | Card title |
| body | 14/20 | 400 | Default UI text |
| small | 13/18 | 400 | Table cell, caption |
| micro-mono | 11/16, Geist Mono, uppercase, +0.04em | 500 | Instrument-label (`RECALL@M_`), status chip |
| stat | 32/32, Geist Mono, tabular | 600 | KPI ticker, blame number |

### Spacing & radii

4px base unit; scale `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`. Radii are **deliberately
varied**, not one constant, to avoid the "identical rounded cards" anti-pattern: KPI
tiles `10px`, standard cards `12px`, the palette/modal surface `16px`, pills/badges
`999px` (full), the tape's step cells `4px` (square-ish, instrument-like), chart
containers `8px`. Hairline border `1px solid line`, `elevated` gets border + 1 step
lighter fill, never a shadow; the palette and the rewind playhead glow use
`box-shadow: 0 0 24px -8px <semantic colour at 35% alpha>` — the one glow per view.

### Spring presets (Motion for React)

| Name | stiffness | damping | mass | Use |
|---|---|---|---|---|
| `snap` | 500 | 34 | 0.7 | Button press, toggle, badge pop |
| `settle` | 260 | 28 | 1 | Card/list-item enter, hover lift |
| `glide` | 160 | 22 | 1.1 | Shared-layout list→detail transition |
| `drift` | 90 | 18 | 1.3 | Rewind fade/replay sequencing, large timeline moves |
| `ticker` | 210 | 26 | 0.9 | Number ticker counting, chart value morph |

`prefers-reduced-motion`: all of the above collapse to a single **120ms linear**
opacity/position cross-fade, no springs, no stagger — durations, not physics.

## 5. Layout blueprints

Each view names its single focal element per the rule in §3.

### Overview — focal: the headline result bars + CI

```
1440px
┌────────────────────────────────────────────────────────────────────────┐
│ [≡] Bisect            Runs  Benchmark  Live  PR checks      [⌘K] [◐]  │
├────────────────────────────────────────────────────────────────────────┤
│  RESULT_                                    ┌ KPI ┐┌ KPI ┐┌ KPI ┐      │
│  ▓▓▓▓▓▓▓▓▓▓▓▓░░░░  treated  58% ±4          │ n   ││ Δ   ││ cost│      │
│  ▓▓▓▓▓▓░░░░░░░░░░  control  31% ±5          └─────┘└─────┘└─────┘      │
│  (animated hero bars, CI whiskers, looping "rewind" behind, dim)        │
├───────────────────────────────┬────────────────────────────────────────┤
│ RECALL@M_            (line)   │ COST_VS_ACCURACY_         (scatter)    │
│                                │                                        │
├───────────────────────────────┴────────────────────────────────────────┤
│ RECENT RUNS_                                              [ view all ] │
│ run-id  sparkline  blame  status  duration                             │
└────────────────────────────────────────────────────────────────────────┘
390px: KPIs become a horizontal scroll-snap row under the hero bars; the two
charts stack full-width; recent runs collapses to 2 visible rows + "view all".
```

### Runs — focal: the filterable table itself (no competing hero)

```
1440px
┌────────────────────────────────────────────────────────────────────────┐
│ Runs   [search___] [status ▾][model ▾][date ▾]              [⌘K][+New] │
├────────────────────────────────────────────────────────────────────────┤
│ ID       Task        Sparkline        Blame stripe   Status   Cost  →  │
│ run-041  refund_bug  ╱╲╱▁▁╱╲           ▓▓▓▓▓░░░ #4    ✓ Pass  $0.42 →  │
│ run-040  order_dup   ▁╱╲▁╱╲            ░░░▓▓▓▓ #6     ✕ Fail  $0.61 →  │
│ … (dense rows, tabular numerals, row hover lifts +2px via `settle`)     │
└────────────────────────────────────────────────────────────────────────┘
390px: sparkline + blame stripe collapse into a single compact glyph column;
row tap opens detail as a shared-layout transition (see §7).
```

### Run detail — focal: the horizontal step timeline with playhead

```
1440px
┌────────────────────────────────────────────────────────────────────────┐
│ ← run-041   refund_bug_investigation           Rewind to: [k=7] [▶ Run] │
├────────────────────────────────────────────────────────────────────────┤
│ TAPE_  ●─●─●─●─●─●─◉─○─○─○─○─○─○      (◉ = playhead, blame glows amber) │
│        heat stripe below: ░░▓▓▓█▓░░░░                                   │
├───────────────────────────────┬────────────────────────────────────────┤
│ STEP INSPECTOR (k=7)          │ FOREST PLOT_          δ                │
│ payload / intervention diff   │  step3  ├──●──┤                        │
│                                │  step5  ├───●─┤                       │
│                                │  step7  ├─────●──┤  ← blame            │
├───────────────────────────────┼────────────────────────────────────────┤
│ DB-STATE DIFF                 │ TREATED vs CONTROL   ●●●○●●○●●●○●●●    │
├───────────────────────────────┴────────────────────────────────────────┤
│ JUDGE vs REPLAY_        agreement 92%   κ 0.81                         │
└────────────────────────────────────────────────────────────────────────┘
390px: tape becomes horizontally scrollable with snap-to-step; forest plot and
dot matrix stack below the inspector; DB diff becomes a collapsible sheet.
```

### Benchmark — focal: the method comparison bars with CI

```
1440px: method bars+CI left two-thirds; heatmap + line stacked right third;
sankey and flaky-world ablation below as full-width bands; cost histogram and
dataset explorer table at the bottom.
390px: method bars stay first and full-width (the focal element travels with
the viewport); everything else stacks in the same order, single column.
```

### Live — focal: the live line + budget gauge cluster

```
1440px: live-line chart spans ~60% width; budget gauge + headroom ring stacked
in a right rail; job queue table and SSE event feed below, full-width.
390px: live-line full-width first, gauge+ring become a horizontal pair under
it, queue/events stack last.
```

### PR checks — focal: base-vs-head delta

```
1440px: base|head split view with a shared central delta column (numbers, not
prose); PR comment preview rendered as an actual GitHub comment mock below.
390px: base/head stack vertically with the delta column becoming inline chips
between them.
```

## 6. Component sourcing plan

### Bklit charts (registry confirmed live at bklit.com/docs/installation; CLI
pattern `npx shadcn@latest add @bklit/<name>`)

| View / need | Bklit component |
|---|---|
| Overview recall@m curve | `@bklit/line-chart` |
| Overview cost-vs-accuracy | `@bklit/scatter-chart` |
| Runs sparkline | `@bklit/line-chart` (compact/sparkline variant) |
| Benchmark method bars + CI | `@bklit/bar-chart` |
| Benchmark heatmap | `@bklit/heatmap-chart` |
| Benchmark line (learning/curve) | `@bklit/line-chart` |
| Benchmark sankey (method→outcome flow) | `@bklit/sankey-chart` |
| Benchmark cost histogram | `@bklit/bar-chart` (binned) |
| Live line | `@bklit/live-line-chart` |
| Live budget gauge | `@bklit/gauge-chart` |
| Live headroom ring | `@bklit/ring-chart` |
| Overview KPI micro-viz (optional) | `@bklit/area-chart` |
| Judge-vs-replay agreement (optional radial) | `@bklit/radar-chart` |

All eleven brief-requested chart types exist in the registry; confirmed slugs also
include `candlestick-chart`, `choropleth-chart`, `composed-chart`, `pie-chart`,
`profit-loss-line`, `sunburst-chart` (unused by Bisect). No chart type from the
brief's list is missing from Bklit — **the forest plot and step timeline go to
visx/d3 per the brief's own split** because neither is a Bklit primitive (forest plot
= custom whisker/dot-per-step plot; timeline = custom scrubbable band with a
draggable playhead), not because Bklit lacks a chart type.

### 21st.dev candidates (community registry — verify license/source in-repo before
installing; 21st.dev components are individually authored and licensing varies per
component, so treat every "as stated" below as needing a second check at install time)

| Need | Candidate | Author | URL | License as stated | Adapt |
|---|---|---|---|---|---|
| Number ticker | Basic Number Ticker | danielpetho | `21st.dev/@danielpetho/components/basic-number-ticker` | Fancy Components collection, MIT-style per 21st norms — **verify at install** | Swap easing for our `ticker` spring, force tabular Geist Mono |
| Command palette | Command Palette | jatin-yadav05 | `21st.dev/community/components/jatin-yadav05/command-palette/default` | Community component — **verify at install** | Restyle to our token set; swap cmdk's default list for icon+detail split (Raycast pattern, §1.2) |
| Hero / animated background | Dot Grid (Shader Builder) | paper-design | `21st.dev/@paper-design/components/dot-grid` | **Apache-2.0**, adapted from Paper Shaders (stated explicitly) | Recolour 4-stop palette to our neutrals + one semantic accent; use only on Overview hero, at low opacity, not full-strength |
| Table | Sortable Table | ddoemonn | `21st.dev/@ddoemonn/components/sortable-table` | Community component — **verify at install** | Strip its default styling to hairline-border + tabular-nums; add sparkline/blame-stripe cell renderers ourselves |
| Tabs, skeletons | shadcn primitives directly (not 21st) | — | shadcn/ui registry | shadcn/ui license (MIT) | Use as-is; no 21st substitute needed, these are commodity primitives |

**Rejected:** any 21st.dev "animated gradient hero" or "purple-to-blue mesh gradient"
result (several appeared in the background/hero searches) — explicitly the anti-pattern
called out in the brief; also rejected generic "glassmorphism" card components that
surfaced in table/background searches, since heavy blur+shadow contradicts the
hairline/flat-elevation rule in §2–4.

## 7. Signature moments

1. **Rewind to k.** Steps `0..k-1` desaturate to `from-tape` slate over `drift`
   (90/18/1.3), 40ms stagger, left to right. Step `k` scales to 1.08× and gains the
   amber→coral glow (our one glow) with a 180ms `settle` pop. Steps `k+1..n` fade to
   opacity 0, then re-enter one at a time *only as replay actually produces them* —
   duration is driven by real replay latency, not a fixed timer (principle 6). A thin
   cyan line sweeps left-to-right underneath, trailing the farthest-replayed step.

2. **Blame reveal.** The blamed step's numeric score counts up from 0 with `ticker`
   (210/26/0.9) in tabular Geist Mono, while a thin amber ring draws around its tape
   cell (SVG stroke-dashoffset, 400ms, `drift`) — ring completes exactly as the ticker
   finishes, so both resolve together.

3. **Forest-plot entrance.** Rows enter top-to-bottom, 60ms stagger; each whisker
   draws outward from the point estimate (`settle`), then the dot pops in with a small
   overshoot. The blamed row is amber and enters last — reads as "found," not "one of
   many."

4. **List → detail (Runs → Run detail).** Shared-layout transition (`layoutId`) on
   the row: ID chip, blame stripe, and status glyph morph into the detail header's
   equivalents over `glide` (160/22/1.1); the rest of the row cross-fades out while
   the tape cross-fades in underneath, anchored where the blame stripe was.

5. **⌘K palette.** Opens a centred floating panel (Raycast layout: filter input, left
   result list with icons, right detail preview), scaling in 0.96→1 with `snap`
   (500/34/0.7) plus a background blur-in — the one element allowed a non-semantic
   glow, since it's chrome, not data. The list filters instantly (no animation, for
   latency); the detail pane cross-fades over 100ms on selection change.

## 8. Anti-patterns checklist

- [ ] No purple-to-blue gradient hero (Overview's hero is result bars + CI).
- [ ] No Inter or Inter-lookalike — Geist/Geist Mono only.
- [ ] No two cards on one screen with identical radius *and* elevation (§4 varies both).
- [ ] No box-shadow as the sole card separator — hairline border + fill-step first;
      glow reserved for the one focal element per view.
- [ ] No decorative colour — every non-neutral pixel maps to a semantic role or isn't
      coloured.
- [ ] No pass/fail conveyed by colour alone — glyph (✓/✕) always present.
- [ ] No blame value shown without its numeric score visible.
- [ ] No animation fabricating progress/timing not backed by a real event (no fake
      "processing" shimmer standing in for the rewind replay itself).
- [ ] No full-strength animated shader/gradient background outside the Overview hero
      (reduced opacity there, never full-strength on dense views).
- [ ] `prefers-reduced-motion` verified to collapse every §4 spring to the 120ms
      linear fallback, per new component, not just shared primitives.
- [ ] No table/list without tabular-numeral alignment on numeric columns.
- [ ] No amber used for anything except blame — audit every PR touching colour.

## Open problems

- 21st.dev component licenses need a second, install-time check — "as stated" above
  reflects search results, not a read of each component's own LICENSE file.
- curated.design's Zoah/Archonum/Oqoqo and WorkOS Atlas/Mintlify/Conductor Build are
  leads only (UNVERIFIED, not opened) — worth a follow-up pass before implementation.
- No benchmark/flaky-world-ablation or PR-comment-preview reference site was found in
  either gallery; those two §5 blueprints are extrapolated, not sourced from a real
  inspected site.
