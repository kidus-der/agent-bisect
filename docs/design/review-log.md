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

---

## Round 3 — 2026-09-17

195 captures in `docs/screenshots/round3/eval/`, same matrix as round 2, now
including the control-arm re-run, the PR-checks gate-history forest plot, the
`HeatLegend` on Runs / Overview / Run detail, and the phone ⌘K preview.

Note on the round-3 brief: `web/e2e/capture/evaluator-capture.ts` was **already
clean**. `npx tsc -b --force`, `eslint` and `prettier --check` all pass on it; the
error two builders saw was fixed in round 2 (`a8a7033`) and their reading was
stale. No capture-script commit was needed this round.

### Scores

| Page | hierarchy | type | colour | motion | data | polish | orig. | **score** | Δ |
|---|---|---|---|---|---|---|---|---|---|
| Overview | 8.5 | 8.5 | 8.0 | 8.0 | 8.5 | 8.5 | 8.5 | **8.4** | +0.3 |
| Runs | 8.5 | 8.5 | 8.5 | 8.0 | 8.5 | 8.5 | 8.5 | **8.4** | +0.3 |
| Run detail | 8.5 | 9.0 | 8.5 | 8.5 | 9.0 | 8.5 | 9.0 | **8.7** | +0.5 |
| Benchmark | 8.5 | 8.5 | 8.0 | 8.0 | 8.5 | 8.0 | 8.5 | **8.3** | +0.2 |
| Live | 8.5 | 8.5 | 8.5 | 8.0 | 8.5 | 8.0 | 8.0 | **8.3** | +0.2 |
| PR checks | 8.5 | 8.5 | 8.5 | 7.5 | 8.0 | 8.0 | 8.5 | **8.2** | +0.2 |
| Global | 8.5 | 9.0 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | **8.6** | 0.0 |

**At or above 8.5: Run detail (8.7) and Global (8.6).** The other four sit at
8.2–8.4. Fourteen of the fifteen round-2 blocking items are fixed and the one
regression is repaired; what is left is no longer about correctness. Each page
below the bar is held there by one or two named criteria, listed under its
heading.

### Verification of round-2 [blocking-8.5] items

| Page | Item | Result |
|---|---|---|
| Overview | 1 ramp anchored on the blamed step | fixed — shared scale excludes the blamed step; `HeatLegend` added |
| Overview | 2 CI whisker floats untied | fixed — on the bar's centreline, caps over the fill |
| Overview | 3 rewind strip's 430px hole | fixed — the tape grew into it |
| Runs | 1 ramp flattening | fixed — cells vary again, legend says `scaled per run` |
| Runs | 2 stripe width varies with step count | fixed — one fixed track, cells divide it |
| Run detail | 1 control re-run says "intervention applied here" | fixed — `fork · control · nothing replaced`, and the control's tape carries no amber |
| Run detail | 2 light blame reads rust | fixed — amber→coral gradient, separable from the fail cell beside it |
| Run detail | 3 dot matrix in a half-empty panel | fixed — a new `DB STATE_` panel sits beside it, promoting the state diff out of a tab |
| Run detail | 4 ramp flattening on the tape | fixed — legend states the real domain, `effect −0.06 … +0.25` |
| Benchmark | 1 390 fold is all preamble | fixed — one mono summary line; two bars clear the fold |
| Live | 1 queued job at 87% | fixed — empty track and `—` |
| Live | 2 light gauge/ring marks ≈1.2:1 | fixed — both clear 3:1 |
| PR checks | 1 390 drops the suite name | fixed — suite stacked under the PR number |
| PR checks | 2 scenario bars have no zero anchor | **partly** — an axis legend was added to the panel header, but the bars still grow leftward from a fixed right edge, so the header and the marks disagree |
| PR checks | 3 empty page below the list | fixed — a `GATE_HISTORY_` panel with a forest plot of all six checks |

Round-2 polish also closed: the tape's actor legend (`USER · AGENT · TOOL`), the
effect caption moved under the tape, a labelled `0` tick on the forest plot, the
⌘K footer's `⏎ open`, a phone ⌘K preview pane, Live's `SUM OF 2 MODELS` /
`TRACES SHARE 0–40`, and `INTERVAL Newcombe 95%` / `TEST two-proportion` as
labelled fields on the gate verdict instead of prose.

### Rule guards

| Guard | Result |
|---|---|
| Amber = blame only, both themes | pass — and the control re-run now correctly carries none |
| Estimate never without its interval | pass |
| Meaning never by colour alone | pass |
| Simulated data labelled | pass |
| No horizontal overflow at 390 | pass |
| Heat-ramp steps legible in both themes | pass — the round-2 regression is repaired, with a legend that states the domain |

---

### Overview — 8.4 (+0.3)

**What separates it from 8.5: colour (8.0) and motion (8.0).** Every other
criterion is already at or above the bar. Colour is held down by the light theme,
where the KPI rail and provenance panel are `#FFFFFF` on `#F5F6F8` and barely
separate from the ground, and by the hero bars' remainder track reading as a
second segment rather than an empty track. Motion has not moved since round 1:
the page's only animated content is the rewind loop, and the KPI numbers, the
headline and the bars all arrive without the ticker and bar-draw the direction
specifies as signature moments (§7.2).

Works: the whisker now sits on the bar it belongs to; the recent-runs stripes
share an origin and a legend; the `PROVENANCE_` panel makes the fold read as an
instrument rather than a dashboard.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/overview/CostAccuracyScatter.tsx` at 1440 — `Bisect` (label at x≈1284) and `Re-run live` (x≈1264) still sit between their two points (x≈1249 and x≈1311), so neither label is clearly owned. Apply the numbered-point + legend treatment that already works at 390, at every width. | [blocking-8.5] |
| 2 | Light theme: move the KPI rail and `PROVENANCE_` to `elevated` `#FBFBFD` so the fill step steps (§2). At present they read as two empty white boxes on a near-white page. | [blocking-8.5] |
| 3 | `features/overview/KpiRow.tsx` — the four KPI numbers appear fully formed. Run them through `useNumberTicker` on the `ticker` spring and let the hero bars draw from 0 on `settle`, so the fold demonstrates the measurement rather than reporting it (§7.2). | [blocking-8.5] |
| 4 | `features/overview/HeadlineBars.tsx` — the remainder track is a distinctly lighter block butted against the fill, so 96.5% reads as two segments. Drop it to `line` at 40%, or remove it and let the axis carry the scale. | [polish] |
| 5 | The blueprint dot texture still runs through the hero paragraph and the bar labels. Mask the dots behind text blocks. | [polish] |
| 6 | The KPI tiles still carry no micro-viz; a 48px sparkline per tile would show direction as well as level (§6). | [polish] |

### Runs — 8.4 (+0.3)

**What separates it from 8.5: motion (8.0), and nothing else.** Six of seven
criteria are at 8.5. The table is static in every capture: rows arrive without
the staggered `settle` entrance the direction specifies, and the row→detail
`layoutId` morph (§7.4) is defined in `motion.ts` but produced no visible
transition in the frame strip.

Works: the stripe column finally means something — one fixed track so step
position is comparable down 266 rows, a ramp that varies again, and a legend that
admits it is scaled per run.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/runs/RunsTable.tsx` — capture `motion-list-to-detail` shows no morph between a row and the detail header. Wire the `layoutIds.runIdChip` / `runBlameStripe` / `runStatus` pairs so the ID chip, stripe and status glyph actually travel on `glide` (§7.4); it is one of the five signature moments and it is the one this page owns. | [blocking-8.5] |
| 2 | Rows enter all at once. Apply `useStagger('settle', STAGGER_SECONDS.list)` to the visible window so the table builds in on first paint, as Bklit's charts do (§2, motion character). | [blocking-8.5] |
| 3 | `SHAPE` and `EFFECT PER STEP` are two step-indexed marks for the same run on two different tracks (x 638–730 and 755–886), so the eye cannot line them up. Put them on one track, or drop `SHAPE` and give its ~120px to the stripe. | [polish] |
| 4 | Sort carets are on `DOMAIN / STEPS / OUTCOME / COST / CALLS` but not `TASK` or `DECISIVE`. Add them or drop the carets, so the header does not imply a capability it lacks. | [polish] |
| 5 | `More filters` shows no count when a filter is hidden behind it. Add a badge. | [polish] |

### Run detail — 8.7 (+0.5) — above the bar

All four round-2 blockers closed, and the `DB STATE_` panel promoted a
brief-required view (`state_before`/`state_after`) out of a tab into the layout.
The page now reads the way the direction statement describes: the tape is the
spine, the numbers are the hero, and every estimate carries its interval.

| # | Fix | Tag |
|---|---|---|
| 1 | The `DB STATE_` panel is 440×250 for three chips and a three-line diff, with ~120px empty below it. Let it size to content, or show the full before/after tree the endpoint returns. | [polish] |
| 2 | `features/run-detail/TimelineMinimap.tsx` — on the 60-step run the visible range is still marked by a 1px line rather than a window. | [polish] |
| 3 | `components/primitives/TapeStep.tsx` — the `scale: 1.08` on the blamed cell (§7.1) is still not detectable in any frame. | [polish] |

### Benchmark — 8.3 (+0.2)

**What separates it from 8.5: polish (8.0), colour (8.0) and motion (8.0).**
Hierarchy and data clarity are at the bar; the page loses its points on small
finishing faults that accumulate — a misaligned axis tick, two right-alignment
axes 110px apart with nothing between, a sankey node too small to hit — and on
two segmented controls styled identically, which the direction explicitly forbids
(§4: vary radius *and* elevation, never two identical control systems on a page).

Works: whiskers on their own track read cleanly against every fill; the 390 fold
now leads with the bars; every sankey node carries its `n`.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/benchmark/MethodComparison.tsx` — the `0% … 100%` axis ends at x≈1150 while the plot's right edge is x≈1128, so the last tick floats outside the plot it labels. Drive the axis off the same scale as the bars. | [blocking-8.5] |
| 2 | The 5-way method segmented control on the histogram and the 2-way `Matrix / Table` toggle are styled identically, so two different kinds of control read as one system. Give them different radii and elevation per §4. | [blocking-8.5] |
| 3 | The right-hand numbers use two right-alignment axes 110px apart (accuracy at x≈1272, cost/calls at x≈1385) with empty space between. Close the gap, or give cost a labelled column header so the second axis is justified. | [blocking-8.5] |
| 4 | `features/benchmark/BlameFlowSankey.tsx` — the `· none · 3` node is still a few pixels tall and cannot be hovered. Give every node a 12px minimum height. | [polish] |
| 5 | At 390 each bar's numbers are right-aligned under a left-aligned bar, so the eye zigzags down the panel. Left-align the numbers under their bars. | [polish] |
| 6 | The dataset table's `DROP` column is the only coral on the page and is not a failure, only a magnitude. It carries a ▼ so it is not colour-alone, but `ink` with the glyph would spend less of the fixed palette. | [polish] |

### Live — 8.3 (+0.2)

**What separates it from 8.5: originality (8.0), polish (8.0) and motion (8.0).**
The measurement half of this page is now correct — axes, a stated shared scale, an
honest queued job, gauge marks that clear 3:1. What holds it back is that half the
page is generic: an event feed where eight rows carry one row of information, and
three job cards that are progress bars. Neither looks like it belongs to a
causal-replay instrument rather than to any monitoring dashboard.

Works: `18.2 · CALLS / MIN · SUM OF 2 MODELS · TRACES SHARE 0–40` says exactly
what the number is and what the axes mean — the clearest chart header in the app.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/live/EventFeed.tsx` — every line reads `simulated: <phase> batch <id> progressed`. Group by batch, show the phase as a mono chip, and put the event's own content in the message, so the feed carries information proportional to its height. | [blocking-8.5] |
| 2 | `features/live/JobQueue.tsx` — a job card is a title, a phase and a bar. A blame job is rewinding to specific steps; show which step it is on and how many of N re-runs are done (`step 7 · 5/16`), which is the thing this product would show and a generic queue could not. | [blocking-8.5] |
| 3 | The two traces are stacked with no shared time cursor, so a spike in one cannot be read against the other at the same instant. Add one hover crosshair across both. | [blocking-8.5] |
| 4 | Nothing on the page animates on arrival except the traces' own advance. The budget gauge and headroom ring should sweep in on `drift` the first time they mount, the way Bklit's charts build (§2). | [polish] |
| 5 | The `● LIVE · 2 updates` count resets with the connection and never says how old the newest frame is. Add `· 2s ago` so a stalled stream is visible. | [polish] |

### PR checks — 8.2 (+0.2)

**What separates it from 8.5: motion (7.5) and data clarity (8.0).** Motion is the
lowest score on any page: the new `GATE_HISTORY_` forest plot is the page's one
real signature moment and it renders fully formed — no row stagger, no whisker
draw, no dot pop (§7.3). Data clarity is held down by the scenario bars, which now
have an axis legend in the panel header that their own geometry does not obey.

Works: the gate-history panel applies the run-detail forest plot's grammar to the
PR level — zero line, per-check interval, flagged in coral and clean in slate —
and that is the right idea, well executed.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/pr-checks/ScenarioTable.tsx` — the header now declares `−67 pts —|— +67 pts`, but the bars still grow leftward from a fixed right edge at x≈822 rather than from the axis's centre. Draw a vertical zero rule down the column at the axis midpoint and anchor every bar on it, so a bar's side says the sign and its length says the size. | [blocking-8.5] |
| 2 | `features/pr-checks/GateSummaryPanel.tsx` — the forest plot's zero line at x≈857 is unlabelled while both domain ends are labelled. A forest plot is read against zero; label the tick. | [blocking-8.5] |
| 3 | `features/pr-checks/GateSummaryPanel.tsx` — the rows arrive fully drawn. Give them the run-detail forest plot's entrance: 60ms stagger, whiskers drawing outward from the estimate on `settle`, dots popping in, flagged rows last (§7.3). | [blocking-8.5] |
| 4 | The gate-history values column is right-aligned at x≈1390 while the plot ends at x≈1035, leaving a 350px gap between a row's mark and its number. Move the values to the plot's right edge. | [blocking-8.5] |
| 5 | The clean rows' slate squares on slate whiskers are hard to locate at this size. Give every point estimate a 1px `ground` outline so it reads against its own interval. | [polish] |
| 6 | Copy: "The rest are inside the noise of a 96-run suite, however their point estimate reads" — should be "whatever their point estimate reads". | [polish] |
| 7 | The detail page's `DECISIVE_STEP_` panel is 540px for two chips and two lines against a 790px comment preview. Give the comment the wider share. | [polish] |
| 8 | At 390 the rows still have no chevron, so the table does not look openable. Add the one the Runs table has. | [polish] |

### Global — 8.6 (0.0) — above the bar

Held its round-2 level and closed two more polish items: the ⌘K footer now reads
`⏎ open`, and the phone palette gained the preview strip the desktop pane has —
outcome, step count, hatched stripe, `0 of 14 steps tested`.

| # | Fix | Tag |
|---|---|---|
| 1 | Light theme: secondary panels are still `#FFFFFF` on `#F5F6F8`. Moving them to `elevated` `#FBFBFD` is the single change that would lift the light theme's colour score on Overview, Runs and Benchmark at once. | [polish] |
| 2 | The error and 404 cards are centred horizontally but pinned near the top with ~440px of blank page below. Centre them in the remaining content height. | [polish] |
| 3 | The ⌘K list still groups only `RUNS` for a run-shaped query; `Pages` / `Commands` / `Copy CLI command` exist but never surface alongside results. Show at least one non-run group for any query that matches one. | [polish] |

---

## Round 4 — 2026-09-17

Reduced scope: only the five pages still below 8.5 were scored. Run detail and
Global carry their round-3 scores forward and were swept once per theme at 1440
— both intact, nothing reported.

**Capture method corrected, and it invalidates part of rounds 1–3.**
`page.screenshot({ fullPage: true })` resizes the viewport under the running page
to stitch, and visx's `ParentSize` re-measures mid-capture, so charts were
recorded at roughly a third of the width the browser actually drew. The script
now opens the viewport to the page's own height and takes an ordinary shot. Two
earlier complaints are withdrawn as artefacts: the Overview scatter and the
Benchmark position chart were never as narrow as rounds 1–3 showed them. The
motion sequences were also wrong: sampling began *after* a settle, so a fast
entrance and a missing one looked identical. Frames now start at the trigger —
the click, or the scroll that reveals a once-only entrance. Round 3's motion
scores were therefore pessimistic, and several "missing" animations turn out to
exist.

### Scores

| Page | hierarchy | type | colour | motion | data | polish | orig. | **score** | Δ |
|---|---|---|---|---|---|---|---|---|---|
| Overview | 8.5 | 8.5 | 8.0 | 8.5 | 8.5 | 8.5 | 8.5 | **8.4** | 0.0 |
| Runs | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | **8.5** | +0.1 |
| Benchmark | 8.5 | 8.5 | 8.5 | 8.0 | 8.5 | 8.5 | 8.5 | **8.4** | +0.1 |
| Live | 8.5 | 8.5 | 8.5 | 8.0 | 8.5 | 8.5 | 8.5 | **8.4** | +0.1 |
| PR checks | 8.5 | 8.5 | 8.5 | 8.0 | 8.0 | 8.0 | 8.5 | **8.3** | +0.1 |
| Run detail | — | — | — | — | — | — | — | **8.7** | carried |
| Global | — | — | — | — | — | — | — | **8.6** | carried |

**At or above 8.5: Runs (8.5), Run detail (8.7), Global (8.6).** Overview,
Benchmark and Live are each 0.1 short and each held there by exactly one
criterion; PR checks is 0.2 short on three.

### Verification of round-3 [blocking-8.5] items

| Page | Item | Result |
|---|---|---|
| Overview | 1 scatter labels ambiguous at 1440 | fixed — numbered points with a two-column legend, at every width |
| Overview | 2 light KPI rail / provenance on near-white | **not fixed** |
| Overview | 3 KPI tickers and hero bars arrive formed | **partly** — the bars now draw from 0 (caught at 67% and 15% of final in frame f01); the KPI numbers still fade in already at their final value |
| Runs | 1 list→detail morph does not happen | fixed — frame f02 catches the status pill, the `Simulated data` pill and the blame chip all in transit to their header positions |
| Runs | 2 rows enter all at once | fixed — f01 shows rows 1–6 painted, 7–8 fading, the rest absent |
| Benchmark | 1 axis last tick outside the plot | fixed |
| Benchmark | 2 two segmented controls styled alike | fixed — `Matrix / Table` is now a text toggle against the bordered method pills |
| Benchmark | 3 two right-alignment axes, nothing between | fixed — `ACCURACY` and `COST` column headers justify the second axis |
| Live | 1 event feed carries one row of information | fixed — phase chip, `×3` grouping and a relative-age column (`now`, `16s ago`) |
| Live | 2 job cards are generic progress bars | fixed — `step-by-step blame search · BLAME_ P5 · DONE 15/16 · CALLS 120 · ETA 59s`; the product's own vocabulary |
| Live | 3 no shared time cursor across the traces | **not fixed** |
| PR checks | 1 scenario bars not anchored on zero | **partly** — a `SCALE_` legend was added to the panel header, but the column still has no zero rule and the legend's centre tick (x≈1060) does not line up with the bars' anchor (x≈823) |
| PR checks | 2 forest zero line unlabelled | fixed — `0` above the line |
| PR checks | 3 forest rows arrive fully drawn | **partly** — frame f00 shows the three flagged whiskers drawn with no point estimates yet, so dots do follow whiskers; but there is no row stagger and the whole entrance is over inside one 70 ms sample |
| PR checks | 4 values column 350px from its marks | **not fixed** |

### Rule guards

All six pass, in both themes and at both widths. Newly checked this round: Live's
headroom ring turns coral at `36.1 rpm in use` but carries the word `tight`
beside it, so the state is not colour-alone.

---

### Overview — 8.4 (0.0)

**One criterion short: colour (8.0).** Everything else is at 8.5. In light theme
the KPI rail and `PROVENANCE_` are `#FFFFFF` on `#F5F6F8` with a `#DEE2E9`
hairline, so the right third of the fold reads as two empty white boxes — the
same finding as rounds 2 and 3, still open. Fixing it is the whole gap.

| # | Fix | Tag |
|---|---|---|
| 1 | Light theme: give the KPI rail and `PROVENANCE_` the `elevated` `#FBFBFD` fill so the fill step actually steps (§2). This one change is what stands between the page and 8.5. | [blocking-8.5] |
| 2 | `features/overview/KpiRow.tsx` — the four numbers fade in already at their final value. Run them through `useNumberTicker` on the `ticker` spring so they count, the way the hero bars now draw (§7.2). | [blocking-8.5] |
| 3 | `features/overview/HeadlineBars.tsx` — the remainder track is a lighter block butted against the fill, so 96.5% reads as two segments. Drop it to `line` at 40%. | [polish] |

### Runs — 8.5 (+0.1) — at the bar

The morph is real: frame f02 catches the status pill, the simulated-data pill and
the blame chip mid-flight between the row and the detail header, and the rows
stagger in top-to-bottom. With the fixed stripe track, the per-run legend and the
chevron, every criterion is now at 8.5. Only two polish items remain (`SHAPE` and
`EFFECT PER STEP` on different tracks; sort carets missing from `TASK` and
`DECISIVE`), and neither is worth spending on.

### Benchmark — 8.4 (+0.1)

**One criterion short: motion (8.0).** The three round-3 items are fixed and
hierarchy, colour, data and polish are all at the bar. No chart on this page was
observed entering: the panels are settled in every frame, so the "charts build in
on scroll-into-view" character the direction takes from Bklit (§2) is not
demonstrated anywhere on the densest chart page in the product.

| # | Fix | Tag |
|---|---|---|
| 1 | Give the method bars, the heatmap cells and the cost histogram a scroll-into-view entrance on `drift`: bars growing from 0, heatmap cells fading in by row, histogram bars rising. That is the whole gap to 8.5. | [blocking-8.5] |
| 2 | `features/benchmark/BlameFlowSankey.tsx` — the `· none · 3` node is still ~6px tall and cannot be hovered. Minimum node height 12px. | [polish] |

### Live — 8.4 (+0.1)

**One criterion short: motion (8.0).** The job cards and the event feed both
became product-specific this round — `DONE 15/16 · CALLS 120 · ETA 59s`, and a
feed with phase chips, `×3` grouping and relative ages — which is what lifted
originality and data clarity to the bar. What is missing is the one interaction a
live page needs.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/live/CallsPerModel.tsx` — the two traces are stacked on a shared 0–40 axis with no shared cursor, so a spike in one cannot be read against the other at the same instant. One hover crosshair spanning both, with both values in the label. That is the gap to 8.5. | [blocking-8.5] |
| 2 | The budget gauge and headroom ring appear fully drawn. Sweep them in on `drift` the first time they mount. | [polish] |

### PR checks — 8.3 (+0.1)

**Three criteria short: data clarity (8.0), polish (8.0), motion (8.0).** The
gate-history forest plot is the right idea and its zero tick is now labelled, but
the page still asks the reader to do work the marks should do: match a bar to a
scale printed somewhere else, and carry a value 350px across empty space to its
own interval.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/pr-checks/ScenarioTable.tsx` — the bars are anchored at x≈823 while the header's `SCALE_` centre tick is at x≈1060, so nothing on screen says where zero is. Draw a 1px zero rule down the column at the bars' anchor and align the header legend to the same x. | [blocking-8.5] |
| 2 | `features/pr-checks/GateSummaryPanel.tsx` — the per-check values are right-aligned at x≈1390 while the plot ends at x≈1035. Move them to the plot's right edge so a row's number sits beside its interval. | [blocking-8.5] |
| 3 | `features/pr-checks/GateSummaryPanel.tsx` — the entrance completes inside one 70 ms sample. Add the 60 ms row stagger and let the whiskers draw outward from the estimate on `settle`, flagged rows last (§7.3). | [blocking-8.5] |
| 4 | The detail page's `DECISIVE_STEP_` panel is 540px for two chips and two lines against a 790px comment preview. Give the comment the wider share. | [polish] |
| 5 | Copy: "however their point estimate reads" → "whatever their point estimate reads". | [polish] |

---

## Round 5 — 2026-09-17

Four pages scored. Runs (8.5), Run detail (8.7) and Global (8.6) carry forward
and were not captured. 56 captures in `docs/screenshots/round5/eval/`, taken with
the corrected method against a real `--fixture` server, frame sequences sampled
from the trigger at 50 ms for 1.2 s.

### Scores

| Page | hierarchy | type | colour | motion | data | polish | orig. | **score** | Δ |
|---|---|---|---|---|---|---|---|---|---|
| Overview | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | **8.5** | +0.1 |
| Benchmark | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | **8.5** | +0.1 |
| Live | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | **8.5** | +0.1 |
| PR checks | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.0 | 8.5 | **8.4** | +0.1 |
| Runs | — | — | — | — | — | — | — | **8.5** | carried |
| Run detail | — | — | — | — | — | — | — | **8.7** | carried |
| Global | — | — | — | — | — | — | — | **8.6** | carried |

**Six of seven pages are at or above 8.5.** PR checks is 0.1 short, on polish
alone, for two copy defects that are visible in the shipped UI.

### Verification of round-4 [blocking-8.5] items

| Page | Item | Result |
|---|---|---|
| Overview | 1 light KPI rail / provenance invisible | fixed — the new light-only `recessed` fill gives both panels a visible ground; my `#FBFBFD` prescription was wrong and the measurement that replaced it (1.136:1 vs 1.046:1) is the right way to have settled it |
| Overview | 2 KPI numbers fade in at final value | fixed — frame f03 catches all four mid-count (`258→266`, `76→86`, `56,029→86,490`, `$0.27→$1.52`) |
| Benchmark | 1 no chart observed entering | fixed — f04 catches the method bars building left-to-right with rows 4–5 not yet present, so the stagger is real and no longer runs underneath the route transition |
| Live | 1 no shared time cursor | fixed — a resting cursor at `now` on both traces, with each trace's value chip beside it and the shared x tick emphasised |
| PR checks | 1 scenario bars not anchored on a visible zero | fixed — a full-column rule at the bars' anchor; the header axis that disagreed with it was removed |
| PR checks | 2 values 350px from their marks | fixed — the gate plot's axis is now bounded by the widest interval (±48, so #1002's CI is no longer clipped), which also closed the gap to the values |
| PR checks | 3 forest entrance completes inside one sample | fixed in shape — frame f00 shows the three flagged rows with whiskers drawn and no point estimates while the clean rows are already complete, so §7.3's order (whisker, then dot, flagged last) is there. It is still faster than the 60 ms-per-row stagger the direction specifies, but the moment reads. |

### Rule guards

All six pass. Newly checked: the budget gauge turns coral at `97% spent · 403
left` and the headroom ring at `tight`, both with the number and the word beside
them, so neither state is carried by colour alone.

---

### Overview — 8.5 (+0.1) — at the bar

Both round-4 items closed. The light theme finally has three legible surfaces on
the fold, and the four KPI numbers count up as the rail enters. Two polish items
remain and neither is worth spending on: the hero bars' remainder track still
reads as a second segment, and the blueprint dots still run through the hero
paragraph.

### Benchmark — 8.5 (+0.1) — at the bar

The densest chart page in the product now demonstrates its own measurements
instead of presenting them finished. One polish item remains: the sankey's
`· none · 3` node is still about 6px tall.

### Live — 8.5 (+0.1) — at the bar

The shared cursor was the last gap and it is a good implementation — resting at
`now` rather than requiring a hover, so the comparison is available before the
reader does anything. With the job cards and the grouped feed from round 4, the
page now reads as this product's live view rather than a generic monitor.

### PR checks — 8.4 (+0.1)

**One criterion short: polish (8.0).** Every other criterion is at the bar: the
zero rule makes the scenario bars readable, the widened axis stopped clipping
#1002's interval and brought the values next to their marks, and the forest
entrance now has its whisker-then-dot order. What is left is two pieces of copy
that ship to the screen.

| # | Fix | Tag |
|---|---|---|
| 1 | `features/pr-checks/ScenarioTable.tsx:74` — the scale key renders `SCALE_ ±67 pts pts · zero at the rule`. `extent` already carries its unit, so the literal ` pts` in `±{extent} pts` duplicates it. | [blocking-8.5] |
| 2 | `features/pr-checks/GateSummaryPanel.tsx` — "The rest are inside the noise of a 96-run suite, however their point estimate reads" should be "whatever their point estimate reads". | [blocking-8.5] |

---

## Round 6 — 2026-09-17 (final)

PR checks scored; one Benchmark sweep to confirm the panel move did no harm.

### PR checks — 8.4 (0.0)

| | hierarchy | type | colour | motion | data | polish | orig. | **score** |
|---|---|---|---|---|---|---|---|---|
| Round 5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.5 | 8.0 | 8.5 | 8.4 |
| Round 6 | 8.5 | 8.5 | 8.5 | 8.5 | **8.0** | **8.5** | 8.5 | **8.4** |

Both round-5 items are fixed: the key now reads `SCALE_ ±67 pts · zero at the
rule` (and `±34 pts` on the clean check, so the extent is per table), and the
gate-history paragraph reads "whatever their point estimate reads". Polish moves
to the bar.

The score does not move, because looking at the 390px captures for the first time
since round 4 turned up a defect on the detail page that the desktop shots hide.

**`features/pr-checks/ScenarioTable.tsx` at 390px drops every numeric column.**
A row renders the scenario name and a coral bar against the zero rule — no
`CHANGE`, no `BASE`, no `HEAD`, no `RUNS`. Eight rows of bar with no value
anywhere on them. At 1440 the same row reads `▼ −67 pts · 93% · 26% · 4`. The bar
is measured against a declared `±34 pts` scale, so it is not meaningless, but a
product whose thesis is a trustworthy number with an interval around it should
not show a magnitude with no magnitude printed (principle 3, "numbers over
narrative"). Keeping `CHANGE` and dropping `RUNS` would fix it.

That is the one thing between this page and 8.5.

### Benchmark sweep

Moving the accuracy heatmap and the blame sankey off the `recessed` fill onto
surface panels did no harm and reads slightly better: the heatmap's ramp
(96% dark teal → 62% pale) and the sankey's flows both sit on white with more
separation than before, while `ACCURACY_BY_POSITION_` keeps the recessed ground
and still reads. Benchmark's 8.5 carries.

### Final scores

| Page | Score | At the bar | Last scored |
|---|---|---|---|
| Run detail | **8.7** | yes | round 3 |
| Global (shell · ⌘K · states · mobile) | **8.6** | yes | round 3 |
| Overview | **8.5** | yes | round 5 |
| Runs | **8.5** | yes | round 4 |
| Benchmark | **8.5** | yes | round 5 (swept round 6) |
| Live | **8.5** | yes | round 5 |
| PR checks | **8.4** | no | round 6 |

**Verdict: six of seven pages are at or above 8.5. PR checks is 0.1 short, on
data clarity alone, because its scenario table renders a bar with no number at
390px.** Every other page clears the bar, every rule guard passes in both themes
at both widths, and the anti-pattern checklist is clean.

Across six rounds the page scores moved 7.1–8.0 → 8.4–8.7. The three faults named
in round 1 as systemic — panels filled to about 40% of the width they occupied,
amber spent on things that were not blame, and estimates shown without their
intervals — are gone. Two of my own round-1–3 findings were wrong and are
withdrawn: the "narrow plot" complaints were a `fullPage` capture artefact, and
several "missing" animations were real but sampled too late to see.
