# Bisect dashboard — design review log

Round-by-round scores from the independent design evaluator. Each round is
captured with `web/e2e/capture/evaluator-capture.ts` against the real app and the
real `--fixture` API, then every screenshot is looked at. Scores are means of
seven criteria, 1–10, judged against `docs/design/direction.md`.

Capture command:

```
uv run python -m agent_bisect.server --fixture --port 8490
cd web && BISECT_API_ORIGIN=http://127.0.0.1:8490 npx vite --host 127.0.0.1 --port 5190 --strictPort
cd web && EVAL_ROUND=<N> npx playwright test --config e2e/capture/evaluator.config.ts
```

---

## Round 1 — 2026-09-17

181 captures in `docs/screenshots/round1/eval/`: every page at 1440×900 and
390×844, dark and light, above-the-fold and full-page; plus filtered Runs, the
mobile filter sheet, four run-detail edge cases (60-step, no-clear, zero-tested,
recording), the rerun view, mid-rewind stills and frame strips, ⌘K with a query,
loading, error, 404, empty, and a reduced-motion pass.

### Scores

| Page | hierarchy | type | colour | motion | data | polish | orig. | **score** |
|---|---|---|---|---|---|---|---|---|
| Overview | 7.0 | 8.5 | 7.5 | 8.0 | 6.5 | 6.5 | 8.5 | **7.5** |
| Runs | 7.0 | 8.5 | 6.5 | 8.0 | 8.5 | 7.0 | 8.0 | **7.6** |
| Run detail | 7.0 | 9.0 | 7.0 | 7.5 | 7.5 | 6.5 | 9.0 | **7.6** |
| Benchmark | 6.5 | 8.5 | 7.0 | 8.0 | 6.5 | 7.5 | 8.5 | **7.5** |
| Live | 7.0 | 8.5 | 6.0 | 8.0 | 5.5 | 7.0 | 7.5 | **7.1** |
| PR checks | 6.0 | 8.5 | 8.0 | 7.5 | 5.5 | 6.0 | 8.0 | **7.1** |
| Global (shell/⌘K/states/mobile) | 8.0 | 9.0 | 7.5 | 8.0 | 8.5 | 6.5 | 8.5 | **8.0** |

**Verdict: every page is below 8.5.** Nothing is broken and the identity is real
— the tape, the registration marks, the underscored mono instrument labels, the
"not bisected yet" state with a copyable CLI line, the empty-tape 404, the
rendered bisect-bot comment. What holds it at "competent, distinctive, unfinished"
is three systemic faults repeated on every page:

1. **Dead space.** Panels are sized to the 1440px grid and filled to ~40%. The
   run-detail dot matrix uses 300 of 1400px. Every PR-check card has a 600px hole
   in the middle. The tape floats centred with 150px gutters. The ⌘K detail pane
   is 90% empty. For a product whose direction statement says "default dense
   throughout", the app reads airy.
2. **Colour-role breaches.** Amber is used for a log level and a connection dot
   on Live — a direct hit on the one rule the direction calls absolute. In light
   theme the blame fill (`#9C5B08`) reads as brick red and is not separable from
   fail coral at a glance.
3. **Estimates without intervals, and marks that encode nothing.** The PR-checks
   list shows `−29 pts` with a p-value but no interval. The scenario table's
   CHANGE bars are the same width on every row. The Live traces have no y-axis.

### Anti-pattern checklist

| Check | Result |
|---|---|
| No purple-to-blue gradient hero | pass |
| Geist / Geist Mono only | pass |
| No two cards with identical radius *and* elevation | **fail** — Overview KPI rail (4), PR-checks list (6) |
| No box-shadow as sole separator | pass (hairline + fill step throughout) |
| No decorative colour | **fail** — `FAULTED PASS` column coloured red; WARN amber |
| Pass/fail never colour alone | pass (✓/✕ glyph present everywhere) |
| No blame value without its score | pass |
| No animation fabricating progress | pass — rewind phases track real state |
| Shader/gradient only on Overview hero | pass |
| `prefers-reduced-motion` collapses every spring | pass — verified, final state at t=120ms |
| Tabular numerals on numeric columns | pass |
| Amber only ever means blame | **fail** — `EventFeed.tsx:9`, `LiveStatus.tsx:32` |

### Motion audit (code + frame strips)

`web/src/design/motion.ts` is correct: five named springs matching §4, `INSTANT`
under reduced motion, stagger collapsing to nothing, transform/opacity only.
Frame strips confirm the rewind staggers left-to-right and the tail re-enters as
replay produces it, and the reduced-motion capture lands on the final state at
120ms with no interstitial frame. Two deviations found:

- `features/overview/RecallCurve.tsx:82` animates its reveal with
  `{ duration, ease: 'easeOut' }` rather than a spring preset.
- The blamed tape cell has two different treatments:
  `components/primitives/TapeStep.tsx:38` (`bg-blame-tint`, no glow) is what the
  run-detail tape renders, while line 115 (`blame-gradient shadow-glow-blame`) is
  what the hero rewind loop renders. Signature moment §7.1 — "step k scales to
  1.08× and gains the amber→coral glow" — is therefore absent on the page that
  matters most.

Vendored Bklit chart code (`components/charts/*`) uses tweens internally; left
alone as vendored.

---

### Overview — 7.5

Works: the headline result reads as a sentence with a number in it and the two
bars carry real CIs; the KPI numerals are big, mono and tabular exactly as §2
asks; the rewind strip with `READ FROM TAPE · 0 CALLS` / `RE-RUN LIVE × 8` bands
is the product's thesis in one glance.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/overview/RunsStrip.tsx` — heat stripes in "Recorded runs" are right-aligned, so a 12-step and a 60-step run put step 1 in different places and blame position cannot be compared down the column. Left-align every stripe to a shared origin and cap the column at a fixed 240px; scale cell width by `240/n_steps`. | [blocking-8.5] |
| 2 | `features/overview/RunsStrip.tsx` — the TASK column is centre-aligned, so task names form a ragged diamond. Left-align it, and pull the columns in: run-id, task, stripe, blame, status should sit in a 4-column grid with `gap: 24px`, not spread across 1370px. | [blocking-8.5] |
| 3 | `features/overview/KpiRow.tsx` — four cards, identical `12px` radius and identical elevation, each ~160px tall for two lines of text, occupying the right third of the fold. Per §4 KPI tiles are `10px` radius; make them a single bordered rail of four rows divided by hairlines (one container, `radius 10px`), height 88px each, and add the micro-viz (`@bklit/area-chart` sparkline, 48px tall) each tile was specced to carry. | [blocking-8.5] |
| 4 | `features/overview/CostAccuracyScatter.tsx` — at 390px the five point labels collide ("Judge · all at once" overlaps "Judge · step by step"; "Bisect" overlaps "Re-run live"). Below 700px switch to a numbered-point + legend-list layout, or run the existing `labelPlacement.ts` with a 16px minimum vertical separation and a leader line. | [blocking-8.5] |
| 5 | `features/overview/RunsStrip.tsx` at 390px — run IDs truncate to `run-…`, which identifies nothing. Give the ID column `min-width: 116px` and truncate the task instead; or drop to one run per card as the Runs page already does well. | [blocking-8.5] |
| 6 | `features/overview/HeadlineBars.tsx` — the CI whisker floats 20px below its bar with no tie. Draw it *inside* the bar's row at the bar's vertical centre as a 1px rule with 6px end caps over the fill, or add a 1px vertical connector from the bar's end down to the whisker. | [blocking-8.5] |
| 7 | `pages/skeletons.tsx` — the Overview skeleton renders 3 KPI slots against 4 real ones, so the rail jumps on load. Make the skeleton's slot count match. | [polish] |
| 8 | The blueprint dot texture runs through the hero paragraph and the "Bisect" / "Judge · step by step" bar labels. Mask the dots behind any text block (`background-clip` or an inset `ground` panel at 92% opacity under the copy). | [polish] |

### Runs — 7.6

Works: the densest, most confident table in the app — mono IDs, tabular numbers,
hatched untested stripes, `DECISIVE` showing step *and* effect; the mobile
card-per-run layout is better than most production tables; the empty state's
empty-tape motif plus `0 runs match` + Clear filters is complete.

| # | Fix | Tag |
|---|---|---|
| 1 | Light theme: the blamed heat-stripe cell renders `#9C5B08`, which reads brick red and is not separable from the fail coral in the same row. Use the amber→coral **gradient** for the blamed cell in both themes (it is a fill, not text, so the AA text floor does not apply) and keep `#9C5B08` only for amber *text*. | [blocking-8.5] |
| 2 | Light theme: non-blame heat-stripe cells sit at roughly 1.4:1 against the white card. They are data marks and need 3:1 (WCAG 1.4.11). Darken the light-theme heat ramp so the lowest step still clears 3:1 on `surface`. | [blocking-8.5] |
| 3 | `pages/RunsPage.tsx` + `features/runs/RunsFilters.tsx` — 235px of page header and three chip rows before row 1, leaving 8 rows above a 900px fold. Drop the page description to one line at 13px, collapse the three chip rows into one row with the inactive groups behind a "More filters" disclosure, and lift the table start to y≈180. Target 13 rows above the fold. | [blocking-8.5] |
| 4 | The table's last visible row is sliced flat at the card edge with no affordance. Add the same 32px `from-surface` bottom fade the tape already uses (`StepTimeline.tsx`) plus a sticky footer showing `n of 266`. | [blocking-8.5] |
| 5 | Two adjacent segmented groups both start with a control labelled "All" (`All/Pass/Fail` and `All/Complete/Recording`), so the page shows two identical-looking selected pills. Label them `OUTCOME_` and `STATUS_` with the same inline mono label treatment `DOMAIN_`/`FAULT_`/`MODEL_` already use. | [blocking-8.5] |
| 6 | The blueprint says each row ends in a `→` affordance; rows are clickable but nothing says so. Add a right-aligned chevron column, 24px, `ink-muted`, going `ink` on row hover. | [polish] |
| 7 | Filter facets disappear between states (MODEL_ vanishes on the empty result). Keep every facet rendered with disabled chips and a `0` count so the chrome does not jump. | [polish] |
| 8 | Mobile filter sheet has no footer: no active-filter count, no Apply/Clear. Add a sticky footer with `Clear all` and `Show N runs`. | [polish] |

### Run detail — 7.6

Works: the blame readout (`+0.88`, its interval, the earliest-step sentence, and
the δ/conf/N/batch/control/boundary config grid) is the best-designed element in
the product; the forest plot has δ, zero line and printed intervals; the "not
bisected" and "recording" states explain themselves and hand you the CLI line.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/run-detail/StepTimeline.tsx:188` — the reset button's label is the word **"Recording"**. It undoes a rewind. Change to `Reset`, and give it `title="Back to the recorded tape"`. | [blocking-8.5] |
| 2 | `features/run-detail/ForestPlot.tsx` — the blamed row draws its point estimate with no visible whisker while every other row has one, so the one row that most needs its interval appears not to have one. Draw the blamed whisker in blame amber at the same 1px weight with 6px caps. | [blocking-8.5] |
| 3 | `components/primitives/TapeStep.tsx:38` — the run-detail tape's blamed cell uses `bg-blame-tint` with no glow or scale, so signature moment §7.1 never happens on the run page. Use the `blame-gradient shadow-glow-blame` variant (line 115) and add `scale: 1.08` on the `settle` spring (260/28/1) when the rewind reaches k. | [blocking-8.5] |
| 4 | `features/run-detail/TapeLane.tsx` — a 12-cell tape is centred inside a 1400px panel, leaving 150px gutters, and a 4-cell recording run leaves ~92% of the panel empty. Left-align the tape to the panel's content edge and let cells grow (`min 40px, max 96px`) to use the width; principle 1 asks for a continuous spine, not a centred motif. | [blocking-8.5] |
| 5 | `features/run-detail/DotMatrix.tsx` — the matrix occupies 300px of a 1400px panel while its `n/16` counts are pinned 900px away at the right edge. Move the counts to immediately after the last cell (`gap: 16px`), and let the cells grow to fill the panel (or halve the panel and pair it with the state diff). | [blocking-8.5] |
| 6 | At 390px the dot-matrix rows are clipped mid-glyph by the count column. Wrap to two rows of 8, or make the row a horizontal scroll-snap strip with the count above it. | [blocking-8.5] |
| 7 | At 390px the Judge-vs-replay heading truncates to "What the judge guessed, and what re-runn…". Headings must not truncate — let it wrap to two lines. | [blocking-8.5] |
| 8 | `features/run-detail/ForestPlot.tsx` — axis ticks are −0.4, −0.1, +0.3, +0.6, +1.0 (uneven steps). Use a `d3-scale` nice-tick generator so the intervals are uniform. | [polish] |

### Benchmark — 7.5

Works: five methods with descriptions, intervals, cost *and* call count in one
row; the hatched no-control ablation bar; the pre-registered bar drawn as a
dashed line with its own chip so the reader sees the target was fixed in advance;
the flaky-world panel states its gap, its interval and "interval excludes zero".

| # | Fix | Tag |
|---|---|---|
| 1 | `features/benchmark/MethodComparison.tsx` — the CI whisker is drawn over the bar in a near-identical value, so its lower cap disappears inside the fill. Draw whiskers in `ink` (dark) / `ground` (light) at 1.5px with 8px caps, on a 6px offset track below the bar, so cap positions are readable against the fill. | [blocking-8.5] |
| 2 | Above the fold at 1440 only one of five method bars is fully visible; at 390 none is. Compress the preamble: page description to one line, and move the `BISECT_ / VS BEST JUDGE_ / PRE-REGISTERED BAR_` strip into the panel header row rather than a full-width nested card. The focal element must clear the fold at both widths (§5). | [blocking-8.5] |
| 3 | `features/benchmark/DatasetExplorer.tsx` — the `FAULTED PASS` column is coloured coral for every row. Red is a fixed role (fail) and this is a rate, not a failure. Render it as `ink` with the drop shown as a `▼ −80 pts` delta chip, or keep both columns neutral and add a small base→faulted slope mark. | [blocking-8.5] |
| 4 | `features/benchmark/PositionSlope.tsx` — the y-axis runs 80–100% while the data occupies 95–97%, so ~85% of the plot is empty. Set the domain from the data's CI envelope with a 10% pad. | [blocking-8.5] |
| 5 | `features/benchmark/BlameFlowSankey.tsx` — no counts on any node; the "no step blamed" sink is a ~4px dot that cannot be seen or hovered. Label each source node `missing field · n = 23` and give the sink a minimum node height of 12px with its count. | [blocking-8.5] |
| 6 | `features/benchmark/CostHistogram.tsx` — an unlabelled dashed vertical line sits near x≈500 calls. Label it or remove it; an unexplained reference line in a measurement tool is worse than none. | [polish] |
| 7 | `features/benchmark/AccuracyHeatmap.tsx` — column headers wrap to two lines of 9px mono (`JUDGE / STEP`). Rotate to a single line at 11px, or shorten to `JUDGE·STEP`. | [polish] |
| 8 | The five-option segmented control on the cost histogram is the same visual weight as the two-option Matrix/Table toggle above it. Vary them per §4 (pills vs. a bordered segment) so they do not read as one system of controls. | [polish] |

### Live — 7.1

Works: the tick-ring budget gauge with `8,366 / of 12,000 calls` is a genuinely
distinctive mark; the traces carry a "now" dot with its value in a chip; the
"Simulated traffic: this server is running on fixtures" line is exactly the
honesty the brief demands.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/live/EventFeed.tsx:9` — `warn: { className: 'text-blame' }`. Amber means blame and nothing else (§3 principle 2). Use `ink` text with the `!` glyph and an `ink-muted` `WARN` tag; reserve colour on this feed for `error` (fail coral) only. | [blocking-8.5] |
| 2 | `features/live/LiveStatus.tsx:32` — `dot: 'bg-blame'` for a connection state. Same rule. Use `ink-muted` for reconnecting and fail coral for disconnected, both with the existing glyph. | [blocking-8.5] |
| 3 | `features/live/CallsPerModel.tsx` — neither trace has a y-axis, so no value on either chart can be read except the trailing one, and the two traces are drawn at equal height on different implicit scales. Add a 3-tick y-axis per trace, and either share one domain across both traces or print the domain in the trace header. | [blocking-8.5] |
| 4 | `features/live/JobQueue.tsx` — `job-0 · blame · 0% · ✓ done` renders a done job with an empty progress track. A finished job must read 100% (or drop the bar and show its duration). | [blocking-8.5] |
| 5 | `features/live/HeadroomRing.tsx` — the filled arc is the *free* headroom, so a nearly-empty ring means "plenty of room", which is backwards from every gauge convention. Fill the *used* portion and keep `10 rpm free` as the centre label. | [blocking-8.5] |
| 6 | The job-queue panel is 3 rows tall inside a 390px panel stretched to match the event feed. Let it size to content and move the event feed full-width beneath, or add the per-job step/ETA rows the height implies. | [blocking-8.5] |
| 7 | Light theme: the budget gauge's unfilled ticks are roughly 1.3:1 on white. They are the mark that shows the remaining budget — bring them to 3:1. | [polish] |
| 8 | `● LIVE · 2 updates` is 12px in a corner on the single page whose whole point is liveness. Promote it to the panel header at `micro-mono` with the pulse, next to the 40.8 KPI (Warp's live-badge pattern, §1.1). | [polish] |

### PR checks — 7.1

Works: the rendered `bisect-bot` comment with its avatar, BOT badge and
definition list is the clearest "this is what lands on your PR" preview in the
app; the clean check leaves `+4.2 pts` deliberately uncoloured because its
interval crosses zero — exactly the right judgment.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/pr-checks/PrChecksPage.tsx` — the list shows `−29 pts` with a p-value and **no interval**. The direction's hardest rule is that an estimate never appears without one. Add `[−40.4, −16.8]` in `micro-mono` under the delta. | [blocking-8.5] |
| 2 | `features/pr-checks/ScenarioTable.tsx` — the CHANGE column's coral bar is the same width on every row regardless of whether the drop is −67 or −44 pts, so the mark encodes nothing. Scale bar width to `|delta| / max|delta|`, anchored at a centre zero line so improvements run the other way. | [blocking-8.5] |
| 3 | `features/pr-checks/PrChecksPage.tsx` — six cards, identical radius and elevation, each with a 600px empty band between title and numbers. Convert the list to a table with the same column discipline the Runs page has (`#PR / verdict / suite / base→head / delta+CI / p`), rows at 52px. | [blocking-8.5] |
| 4 | `features/pr-checks/DecisiveStepChange.tsx` — the panel ships the sentence "This endpoint does not return them as fields, so they are not restated here as if they were." That is an implementation note, not product copy. Delete it; if the effect is genuinely unavailable here, say `effect not returned by this endpoint · see the comment below` in `micro-mono`. | [blocking-8.5] |
| 5 | The base/head mini-bars in the list are unlabelled, so base-vs-head is carried by grey-vs-colour alone. Add `B` / `H` `micro-mono` prefixes, or drop the bars from the list (fix 3 makes them redundant). | [blocking-8.5] |
| 6 | On a clean check the decisive-step panel reads `none → none · unchanged` plus three paragraphs — a half-page of nothing. Collapse it to one line when both refs are `none`. | [blocking-8.5] |
| 7 | `features/pr-checks/PassRateCompare.tsx` — on a clean check the head bar is pass-green while the delta is deliberately neutral, so the panel says "better" and "not significant" at once. Keep both bars slate when the interval crosses zero. | [polish] |
| 8 | At 390px the mini-bars are dropped entirely and the delta/p line wraps right-aligned, leaving each card ragged. Give the mobile card a two-column footer grid: `base→head` left, `delta + p` right. | [polish] |

### Global — 8.0

Works: `SIMULATED DATA` is present on every page at every width, so the
simulated-data rule is honoured without exception; the empty-tape 404 and the
`Cannot reach the Bisect server. Is \`bisect serve\` running?` error copy are
specific and useful; reduced motion verifiably lands on final state at 120ms.

| # | Fix | Tag |
|---|---|---|
| 1 | Overview shows a full skeleton for ~20s before the error surfaces (query retries), so a dead server looks like a slow one. After the first failure, show `retrying… (2 of 3)` in the panel header. | [blocking-8.5] |
| 2 | `app/CommandPalette.tsx` — the right detail pane holds an icon, a title, a subtitle and a path chip, then ~200px of nothing. Put the run's real preview there: outcome glyph, step count, blame chip with its interval, and the heat stripe. It is the pane's whole reason to exist (§7.5, Raycast). | [blocking-8.5] |
| 3 | `app/CommandPalette.tsx` — the result list is sliced flat mid-row at the panel's bottom edge. Add a bottom fade and make the list height a whole multiple of the 40px row. | [blocking-8.5] |
| 4 | Error and 404 cards are 1376px wide with content in the top-left 400px and an empty page below. Constrain the state card to `max-width: 560px` and centre it in the content area. | [blocking-8.5] |
| 5 | `app/BrandMark.tsx` uses `--bx-blame-coral` in the logo gradient. Amber/coral is reserved for blame; give the mark its own neutral or cyan treatment so the one semantic colour is not spent on chrome. | [polish] |
| 6 | `features/overview/RecallCurve.tsx:82` uses `{ duration, ease: 'easeOut' }` instead of a `settle`/`drift` spring. Springs only for UI state (§4). | [polish] |
| 7 | Every ⌘K result carries the same tag icon and the only group is `RUNS`. Add page and action groups with distinct icons so the palette is a command palette, not a run search. | [polish] |
| 8 | Light theme: `surface` `#FFFFFF` cards on `ground` `#F5F6F8` with a `#DEE2E9` hairline give very little separation, which is why the light KPI rail reads as four empty boxes. Use `elevated` `#FBFBFD` for secondary cards so the fill step actually steps (§2). | [polish] |
