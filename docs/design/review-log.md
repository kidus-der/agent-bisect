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

---

## Round 2 — 2026-09-17

195 captures in `docs/screenshots/round2/eval/`, same matrix as round 1 plus the
⌘K run-preview pane, the `retrying… (n of 3)` state, the treated **and** control
re-run views at both widths, the PR-checks table, and Live waited on real SSE
frames from the fixture server.

### Scores

| Page | hierarchy | type | colour | motion | data | polish | orig. | **score** | Δ |
|---|---|---|---|---|---|---|---|---|---|
| Overview | 8.0 | 8.5 | 8.0 | 8.0 | 7.5 | 8.0 | 8.5 | **8.1** | +0.6 |
| Runs | 8.5 | 8.5 | 8.5 | 8.0 | 7.0 | 8.5 | 8.0 | **8.1** | +0.5 |
| Run detail | 8.0 | 9.0 | 7.5 | 8.5 | 8.0 | 7.5 | 9.0 | **8.2** | +0.6 |
| Benchmark | 7.5 | 8.5 | 8.0 | 8.0 | 8.5 | 8.0 | 8.5 | **8.1** | +0.6 |
| Live | 8.5 | 8.5 | 7.5 | 8.0 | 8.0 | 8.0 | 8.0 | **8.1** | +1.0 |
| PR checks | 8.0 | 8.5 | 8.5 | 7.5 | 7.5 | 8.0 | 8.0 | **8.0** | +0.9 |
| Global | 8.5 | 9.0 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | **8.6** | +0.6 |

**Global has reached 8.5.** The six content pages sit at 8.0–8.2 — every one is
now a polished professional product with a clear identity, which is the 8.5
anchor's description, held just below it by a small number of specific faults
rather than by anything systemic. The three systemic faults named in round 1 are
gone: the dead space is largely filled, both amber breaches are repaired, and
every estimate now carries its interval.

### Verification of round-1 [blocking-8.5] items

| Page | Item | Result |
|---|---|---|
| Overview | 1 stripes right-aligned | fixed — shared left origin, comparable down the column |
| Overview | 2 TASK centre-aligned | fixed |
| Overview | 3 four identical KPI cards | fixed — one hairline-divided rail, plus a new `PROVENANCE_` panel that fills the rail's old dead space |
| Overview | 4 scatter labels collide at 390 | fixed — numbered points with a legend below |
| Overview | 5 run IDs truncate at 390 | fixed — the task truncates instead |
| Overview | 6 CI whisker floats untied | **not fixed** |
| Runs | 1 light blame fill reads brick red | fixed on Runs — now a clear amber→coral, separable from fail red |
| Runs | 2 light heat cells ≈1.4:1 | fixed — solid mid-teal, clears 3:1 |
| Runs | 3 only 8 rows above the fold | fixed — one filter row + `More filters`, 12 rows |
| Runs | 4 last row sliced, no fade | fixed — fade plus a sticky `266 of 266` |
| Runs | 5 two segments both labelled "All" | fixed — `OUTCOME_` / `STATUS_` |
| Run detail | 1 reset button says "Recording" | fixed — "Reset" |
| Run detail | 2 blamed forest row has no whisker | fixed — amber whisker with caps |
| Run detail | 3 blamed tape cell has no glow | fixed for the glow; the 1.08× scale is not detectable |
| Run detail | 4 tape centred with 150px gutters | fixed — spans the panel, cells grow |
| Run detail | 5 dot matrix 300 of 1400px | fixed — counts adjacent, column ticks added |
| Run detail | 6 dot matrix clipped at 390 | fixed |
| Run detail | 7 h2 truncated at 390 | fixed — wraps |
| Benchmark | 1 whiskers drawn over the bars | fixed — own track below each bar |
| Benchmark | 2 focal bars below the fold | fixed at 1440; **not fixed at 390** |
| Benchmark | 3 `FAULTED PASS` coloured red | fixed — neutral, with a new `DROP` column carrying a ▼ glyph |
| Benchmark | 4 position chart 85% empty | fixed — axis rescaled to the CI envelope |
| Benchmark | 5 sankey has no counts | fixed — every node labelled, `· none · 3` visible |
| Live | 1 amber WARN | fixed — `text-ink` |
| Live | 2 amber live-status dot | fixed — `bg-ink-muted` |
| Live | 3 no y-axis on the traces | fixed — axes plus `SCALE 0–40 SHARED` in the header |
| Live | 4 done job at 0% | fixed — 100% |
| Live | 5 ring fills the free portion | fixed — fills used, centre reads free |
| Live | 6 job-queue panel half empty | fixed — three cards across the width |
| PR checks | 1 delta without its interval | fixed — `CHANGE · 95% CI` on every row |
| PR checks | 2 scenario bars all one width | fixed — they scale |
| PR checks | 3 six identical cards, 600px hole | fixed — a sortable table |
| PR checks | 4 implementation-note paragraph | fixed — `EFFECT NOT RETURNED HERE · SEE THE COMMENT BELOW_` |
| PR checks | 5 unlabelled base/head bars | fixed — BASE / HEAD columns |
| PR checks | 6 decisive-step panel dead weight when clean | fixed — one line |
| Global | 1 dead server looks slow for 20s | fixed — `RETRYING… (2 OF 3)` with the reason |
| Global | 2 ⌘K detail pane 90% empty | fixed — outcome, step count, hatched stripe, `0 of 14 steps tested` |
| Global | 3 ⌘K list sliced mid-row | fixed — fades |
| Global | 4 error/404 cards 1376px wide | fixed — ~560px, centred |

Round-1 polish items also closed: skeleton KPI slot count, `BrandMark` no longer
spends blame coral, `RecallCurve` now uses the `drift` spring, the palette has
`Pages` / `Commands` / `Copy CLI command` groups, the histogram's dashed rule is
labelled, the heatmap headers fit one line, and a clean check no longer paints
its head bar green against a non-significant delta.

### Rule guards

| Guard | Result |
|---|---|
| Amber = blame only, both themes | pass in code (`EventFeed`, `LiveStatus`, `BrandMark` all cleared); light blame still reads rust on the run-detail heat stripe |
| Estimate never without its interval | pass — PR list, forest plot, method bars, ablation, gate verdict all carry theirs |
| Meaning never by colour alone | pass — ✓/✕ glyphs, ▼ on deltas, `!` on WARN, hatching on untested and on the ablation bar |
| Simulated data labelled | pass — badge on every page, `Simulated traffic` on Live, `Simulated data` on run detail |
| No horizontal overflow at 390 | pass on every page captured |
| Heat-ramp steps legible in both themes | **fail** — legible, but the ramp no longer varies (below) |

### The one regression

Fixing the light-theme heat-stripe contrast flattened the ramp in **both**
themes. In round 1 the `EFFECT PER STEP` cells varied; in round 2 every tested
non-blame cell is one teal, on Runs, on Overview and on the run-detail tape. The
cause is visible in the data: `brief-12-step` has effects from −0.06 to +0.25
plus a blamed +0.88, so a linear ramp anchored on the maximum puts every ordinary
step inside the bottom 28% of the scale, where the steps are indistinguishable. A
column titled "effect per step" now encodes only tested / blamed / untested.

---

### Overview — 8.1 (+0.6)

Works: the fold is now dense and correctly ranked — headline, bars with intervals,
KPI rail, provenance; the new `PROVENANCE_` panel (agent, user sim, τ² commit,
generated-at) is exactly the instrument-panel move the direction asks for; the
recent-runs stripes finally share an origin, so blame position reads down the column.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/overview/RunsStrip.tsx` + `features/runs/cells.tsx` + `features/run-detail/heatScale.ts` — the effect ramp is anchored on the blamed step, so every ordinary step collapses to one value. Build the ramp's domain from the tested effects **excluding** the blamed step (or use a quantile scale over them) and keep the blamed cell on its own amber→coral treatment outside the ramp. | [blocking-8.5] |
| 2 | `features/overview/HeadlineBars.tsx` — the CI whisker still floats ~28px below its bar with nothing tying them. Put the whisker on the bar's own centreline as a 1px rule with 6px caps drawn over the fill, or add a 1px vertical connector from the bar's end to the whisker. | [blocking-8.5] |
| 3 | The rewind strip panel has ~430px of empty canvas between the tape (ends x≈630) and the step-7 diff block (starts x≈1060) at 1440. Either let the tape's cells grow into it as the run-detail tape now does, or move the diff block directly under the tape and halve the panel's height. | [blocking-8.5] |
| 4 | The blueprint dot texture still runs through the hero paragraph and the `Bisect` / `Judge · step by step` bar labels. Mask the dots behind text blocks. | [polish] |
| 5 | `features/overview/labelPlacement.ts` at 390 — the point index digits are drawn on top of their own CI whisker stroke. Offset the digit 6px to the right of the whisker, or give it a 2px `ground` halo. | [polish] |
| 6 | The hero bars' remainder track renders as a distinctly lighter block butted against the fill, so a 96.5% bar reads as two segments. Drop the track to `line` at 40% or remove it and let the axis carry the scale. | [polish] |
| 7 | The KPI rail still has no micro-viz; a 48px `@bklit/area-chart` sparkline per tile would let the four numbers show direction as well as level (§6). | [polish] |

### Runs — 8.1 (+0.5)

Works: the densest, most confident view in the product — 12 rows above the fold,
one filter row with instrument-labelled groups, a sticky `266 of 266`, a chevron
per row, and a fade instead of a slice; light-theme blame is now unmistakably
amber→coral and no longer confusable with fail red.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/runs/cells.tsx` — same ramp flattening as Overview fix 1. `EFFECT PER STEP` must vary with the effect, or the column should be renamed to what it actually shows. | [blocking-8.5] |
| 2 | The heat stripe's cell width is constant, so a 27-step run's stripe is more than twice as wide as an 11-step run's and the column is ragged. Fix the stripe's total width and divide it by `n_steps`, so every stripe spans the same track and step *position* stays comparable. | [blocking-8.5] |
| 3 | `SHAPE` and `EFFECT PER STEP` are two adjacent step-indexed marks for the same run with no shared x. Align them to the same track, or drop `SHAPE` and give the freed ~120px to the stripe. | [polish] |
| 4 | `More filters` gives no indication of how many filters are hidden behind it or whether any are active. Add a count badge when the disclosure holds an active filter. | [polish] |
| 5 | Sort affordances are on `DOMAIN / STEPS / OUTCOME / COST / CALLS` but not `TASK`, `SHAPE`, `EFFECT PER STEP`, `DECISIVE`. Either make `TASK` and `DECISIVE` sortable or drop the carets so the header does not imply a capability it lacks. | [polish] |

### Run detail — 8.2 (+0.6)

Works: all eight round-1 blockers closed; the tape now spans its panel and the
blamed cell glows; the forest plot has a uniform axis, a zero line, a δ line and
an amber interval on the blamed row; the new recorded-vs-re-run side-by-side on
the rerun page, with its closing sentence, is the clearest thing in the product.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/run-detail/RerunView.tsx` — a **control** re-run's fork step is labelled `fork · intervention applied here`. The control arm is defined by having nothing replaced; this sentence contradicts the product's central claim. Render `control · nothing replaced` when `arm === 'control'`, and change the closing line to say the control differs from the recording only by its seed. | [blocking-8.5] |
| 2 | Light theme: the run-detail heat stripe's blamed cell renders rust/brick (`#9C5B08` at full fill) while the header's `STEP 7` chip beside it is bright amber, so the same role has two readings on one screen. Use the same amber→coral gradient Runs now uses for the blamed cell. | [blocking-8.5] |
| 3 | `features/run-detail/DotMatrix.tsx` — the matrix plus counts now ends at x≈700 inside a 1360px panel, leaving half of it empty. Put the state diff (currently a tab inside the inspector) beside it, or halve the panel and let it sit next to the forest plot. | [blocking-8.5] |
| 4 | Same ramp flattening on the tape's heat stripe as Overview fix 1. | [blocking-8.5] |
| 5 | `features/run-detail/TimelineMinimap.tsx` — on the 60-step run the minimap marks the viewport with a single 1px line rather than a window, so it does not show how much of the tape is off-screen. Draw the visible range as a bordered window. | [polish] |
| 6 | The caption `step 7 effect +0.88 [+0.47, +0.96]` sits at the panel's far left while step 7 is at x≈595. Anchor it under the playhead, or move it into the `BLAME_` rail where the same numbers already live. | [polish] |
| 7 | The step actor glyphs above each tape cell (person / robot / wrench) are never explained. Add a one-line mono legend in the tape header: `user · agent · tool`. | [polish] |
| 8 | `components/primitives/TapeStep.tsx` — the `scale: 1.08` on the blamed cell called for by §7.1 is not visible in any frame. Confirm it is applied and raise it if the border is absorbing it. | [polish] |

### Benchmark — 8.1 (+0.6)

Works: the CI whiskers now have their own track and read cleanly against the
fills; the sankey names every node with its `n`; the histogram carries a labelled
`Bisect · 780 calls` rule and a mean-calls footer for all five methods; the
dataset table's new `DROP` column shows the fall with a ▼ rather than colour.

| # | Fix | Tag |
|---|---|---|
| 1 | At 390 the fold is still all preamble: page title, panel title, description and a stacked `96.5% / +15.1 pts / met · 96.4%` strip consume ~700px and not one bar is visible. Below 700px render the summary strip as a single mono line (`96.5% [90.2, 98.8] · +15.1 pts vs best judge · pre-registered 96.4% ✓`) so the bars clear the fold, as §5 requires. | [blocking-8.5] |
| 2 | The `0% … 100%` axis under the bars ends at x≈1150 while the plot's right edge is x≈1128, so the last tick sits outside the plot. Align the axis to the plot's scale. | [polish] |
| 3 | The right-hand numbers use two right-alignment axes 110px apart (accuracy at x≈1272, cost/calls at x≈1385) with nothing between. Close the gap or give cost its own labelled column header. | [polish] |
| 4 | The 5-way method segmented control on the histogram and the 2-way `Matrix / Table` toggle are styled identically, so they read as one control system. Vary them per §4 (pills vs. a bordered segment). | [polish] |
| 5 | The sankey's `· none · 3` node is still only a few pixels tall. Give every node a minimum height of 12px so a small-but-real outcome stays clickable and visible. | [polish] |

### Live — 8.1 (+1.0)

Works: the biggest jump of the round — both amber breaches repaired, both traces
given y-axes with `SCALE 0–40 SHARED` stated in the header so the two are
honestly comparable, the ring now fills what is used, and the job queue became
three cards across the full width instead of a half-empty column.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/live/JobQueue.tsx` — `job-0 · BLAME_ · queued · 87%` shows a queued job with a mostly-full progress bar. A queued job has not started; show a dash or an empty track and put the 87% behind whatever it actually measures. | [blocking-8.5] |
| 2 | Light theme: the budget gauge's unfilled ticks and the headroom ring's track are roughly 1.2:1 on white. Both are data marks showing the remaining portion and need 3:1 (WCAG 1.4.11). Darken the light-theme track token. | [blocking-8.5] |
| 3 | `features/live/EventFeed.tsx` — every line reads `simulated: <phase> batch <id> progressed`, so eight rows carry about one row of information. Show the phase as a mono chip, the batch id once per group, and the event's own detail in the message. | [polish] |
| 4 | `50.4 CALLS / MIN · SCALE 0–40 SHARED` — the total is 50.4 while the shared axis tops out at 40, so the headline number is off the scale it sits above. Either label the total as a sum across models or extend the axis. | [polish] |
| 5 | The two traces are stacked with no shared time cursor. A single hover crosshair across both would let a spike be read against the other model at the same instant. | [polish] |

### PR checks — 8.0 (+0.9)

Works: the list is now a sortable table where every row carries `−38 pts` **with**
`[−48 pts, −25 pts]`; a clean check's decisive-step panel has collapsed to one
line and its bars stay slate against a non-significant delta — the restraint is
right; the `bisect-bot` comment preview remains the clearest artefact in the app.

| # | Fix | Tag |
|---|---|---|
| 1 | At 390 the table drops the `SCENARIO SUITE` column, so six rows read `#1002 · regression · −38 pts` with no indication of which suite regressed. The suite name is the row's identity — keep it and drop `P` instead, or stack it under the PR number. | [blocking-8.5] |
| 2 | `features/pr-checks/ScenarioTable.tsx` — the CHANGE bars now scale, but they grow leftward from a fixed right edge with no zero line and no axis, so a bar's length has no reference. Anchor them on a centre zero line with the axis labelled once in the header. | [blocking-8.5] |
| 3 | The list page is one 400px panel on a 900px viewport with ~260px of empty page under it. Add the thing a reviewer wants next to the table — a small base-vs-head distribution across all six checks, or the most recent gate comment — or let the table fill the height. | [blocking-8.5] |
| 4 | The detail page's `DECISIVE_STEP_` panel is 540px wide holding two chips and two short lines, against a 790px comment preview beside it. Give the comment preview the wider share. | [polish] |
| 5 | At 390 the rows have no chevron and no `BASE`/`HEAD`, so the table reads as a static list rather than something to open. Add the chevron the Runs table now has. | [polish] |

### Global — 8.6 (+0.6) — at the bar

Works: `RETRYING… (2 OF 3)` with the reason means a dead server no longer looks
like a slow one; the ⌘K detail pane now previews the run — outcome, step count,
hatched stripe, `0 of 14 steps tested`, `Not bisected yet.`; error and 404 are
sized cards rather than banners in a 1376px void; the logo no longer spends blame
coral, and the palette has real `Pages` / `Commands` / `Copy CLI command` groups.

| # | Fix | Tag |
|---|---|---|
| 1 | The error and 404 cards are centred horizontally but pinned near the top, leaving ~440px of empty page below. Centre them in the remaining content height. | [polish] |
| 2 | The ⌘K footer's `⏎ run` reads as a verb. `⏎ open` says what the key does. | [polish] |
| 3 | Light theme: secondary cards are still `#FFFFFF` on `#F5F6F8`, so the fill step barely steps. Move secondary panels to `elevated` `#FBFBFD` (§2). | [polish] |
