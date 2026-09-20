# Bisect — walkthrough content

Source content for the orchestrator's walkthrough Artifact (five tabs). Not
published from here — the Artifact tool publish is the orchestrator's step.
Numbers marked `{{P5_TEST}}` are pending P5's test split (running live as
this is written); everything else is real. Brief:
https://claude.ai/artifact/E8CNvEPBrbnfH9M7JtSZCe

**The 12 curated screenshots**, all at `docs/screenshots/final/`, suggested
placement by tab:

| Tab | File | Use |
|---|---|---|
| 1 — What we built | `overview-dark-1440.png` | the headline result and its interval |
| 1 — What we built | `run-detail-rewind-dark-1440.png` | the rewind mid-flight: tape desaturates behind the playhead, blamed step glows amber |
| 2 — Step by step | `run-detail-dark-1440.png` | the tape, forest plot and step detail together |
| 2 — Step by step | `pr-check-detail-dark-1440.png` | the PR-check example rendered for real |
| 3 — Where we are | `benchmark-dark-1440.png` | method comparison bars, heatmap, flaky-world ablation |
| 3 — Where we are | `runs-dark-1440.png` | the run list / benchmark browser |
| 3 — Where we are | `live-dark-1440.png` | the live SSE view of a run in progress |
| 4 — Moving forward | `palette-dark-1440.png` | the design system reference (useful if discussing what's reusable) |
| 5 — Test it locally | `overview-light-1440.png` | light theme, for anyone judging by that alone |
| 5 — Test it locally | `overview-dark-390.png` | mobile width, Overview |
| 5 — Test it locally | `run-detail-dark-390.png` | mobile width, Run detail |
| 5 — Test it locally | `run-detail-light-1440.png` | light theme, Run detail |

---

## Tab 1 — What we built

**The one-line version:** `git bisect`, for agent runs. When an AI agent
fails a task, Bisect rewinds the run to a specific step, changes exactly
one thing, replays the rest of the run several times, and tells you —
with a confidence interval, not a guess — whether that step actually
caused the failure.

**The problem it solves.** Today, when an agent fails, the usual way to
find out why is to hand the transcript to another AI model and ask it to
read through and guess which step went wrong. That's an opinion, not a
measurement — it's cheap, but it's often wrong, and it never tells you how
confident to be. Published numbers put a judge's accuracy at finding the
right step around 14–36% on realistic benchmarks.

**What Bisect does instead.** It treats the question like a scientist
would: don't just look, test it. Take the run's recorded steps, pick a
suspect step, change what happened at that step (fix a bad tool result, for
instance), and re-run the rest of the trajectory several times to see if
the outcome changes. Compare that against a **control** — re-running the
same steps *without* the fix — so you're not fooled by an agent that just
happens to succeed sometimes anyway. The step whose fix reliably flips
failure into success, measured with a real statistical interval, is the one
that gets the blame.

**The four pieces:**
- **A recorder** that writes down every step of a run — the exact request
  sent to the model, the tool call, and a snapshot of the world before and
  after — so nothing has to be re-imagined later.
- **A replay engine** that can rewind to any step and either play back
  exactly what happened (free, instant, no model calls) or let the rest of
  the run happen live from there.
- **A statistics engine** that runs the treated-vs-control comparison
  properly — the same style of interval used in clinical trials — and
  decides, step by step, which one first crosses the bar for "this
  mattered."
- **A dashboard and a GitHub Action** that put this in front of a person:
  browse a run, watch the rewind happen, see the blamed step highlighted,
  or get a comment on a pull request the moment a code change measurably
  breaks the agent, naming the exact step that broke.

**Why this is hard to get right.** An agent's world can be genuinely
unpredictable (a live database that changes, a clock that moves, an
occasional flaky error), and any tool that claims to safely "rewind" that
world has to prove it doesn't quietly lie about what would have happened.
Bisect proves it offline, deterministically: restoring a recorded snapshot
reproduces the exact same world state 100% of the time; re-running the same
calls against a live, unpredictable system reproduces it 0% of the time.
That gap is the whole argument for why snapshots matter.

---

## Tab 2 — Step by step

Here's the method end to end, using the numbers that describe the design
(not any specific run):

1. **Record.** Every step of an agent run — what was asked, what tool was
   called, what came back, what the world looked like before and after —
   gets written down permanently. Nothing about this step needs a live
   model call ever again.
2. **Shortlist the suspects.** An AI judge reads the failed run and picks up
   to 3 steps it thinks might be the cause. This isn't the final answer —
   it's a shortlist, the same way a doctor orders a few tests instead of
   running every test that exists.
3. **Rewind.** For each suspect step, the world gets restored to exactly
   how it looked right before that step — verified against a recorded hash,
   so there's no ambiguity about whether the rewind actually worked.
4. **Change one thing, and run it both ways.** One version fixes the
   suspected problem at that step and lets the rest of the run play out
   live, multiple times. Another version (the control) changes nothing and
   also lets the rest play out live, the same number of times. Both use the
   real model, the real tools, the real randomness a live system has.
5. **Compare, with a number attached.** If the fixed version passes a lot
   more often than the control, that's evidence the step mattered — and the
   size of that "a lot more often" comes with a confidence interval, so you
   know whether it's a strong signal or a coin flip that happened to look
   good.
6. **Blame the earliest step that clears the bar.** Not the step with the
   single biggest effect — the earliest one whose evidence is strong enough
   — because a later step "helping" doesn't undo the damage an earlier step
   already did.

**What this looks like on a pull request** (the actual mechanism the GitHub
Action uses, illustrated with realistic numbers, not a real run):

```
Bisect · agent regression detected
scenario suite     airline-refunds (24 tasks × 4 runs)
pass rate          base 0.83  →  head 0.54   (p = 0.002)
decisive step      step 7 · agent → get_reservation_details
effect of reverting at step 7   +0.62  95% CI [0.38, 0.81] · N = 12
what changed at step 7
  - asks for the reservation ID before looking anything up
  + looks up the most recent reservation by user_id
  caused by: system_prompt.md L31–L36 (this PR)
7 of 13 new failures share this step · 212 model calls · details → bisect serve
```

The pass-rate drop has to be both statistically real (not noise) and at
least 10 percentage points before Bisect says anything at all — a PR that
only wobbles a little never gets flagged.

---

## Tab 3 — Where we are

**Honest status, as of this writing: P5 (the headline evaluation) is still
running.** Everything else — building the tool, proving the statistics
work on synthetic data, building the dataset of real planted failures,
shipping the dashboard, and shipping the GitHub Action — is done and
measured.

**What's finished and measured:**

- **The core engine** (recording, replay, rewind, the statistical
  estimator) is built and passes its own tests: every recorded run
  replays byte-for-byte identically with zero network calls, and a
  tampered request is caught and rejected rather than silently allowed
  through.
- **The estimator was proven on synthetic data first**, where the "right
  answer" is known in advance, before it ever touched a real failure.
  It found the planted cause **89.5%** of the time against a 95% target —
  short of the target, but for an understood, structural reason (with only
  16 re-runs per comparison, some genuinely real effects are just too
  subtle to detect reliably; more re-runs would close the gap, at a
  proportional cost). The team fixed a real statistical bug along the way
  (acting too early on noisy early evidence) that eliminated every false
  accusation entirely.
- **A dataset of real planted failures was built**: take a real agent task
  it solves correctly, plant one realistic mistake (a wrong tool answer, a
  missing field, stale information, a tool error), and see if that alone
  is enough to make it fail consistently. Out of 292 real attempts, only
  18 (about 6%) actually broke the agent reliably — which is itself an
  interesting finding: this agent usually shrugs off a single planted
  mistake and recovers on its own. That's fewer labelled failures than
  originally planned for, and it's reported honestly rather than quietly
  padded.
- **The dashboard is built and working**, showing the tape of a run, the
  rewind animation, the statistical comparison as a forest plot, and the
  benchmark results — evaluated for usability and accessibility, both
  passing.
- **The GitHub Action works on real pull requests**: tested against 6 real
  PRs on the public repository, it correctly caught all 3 real regressions
  (naming the right step every time) and stayed quiet on all 3 harmless
  changes.

**What's still running:** the final head-to-head comparison — does Bisect
actually beat an AI judge at finding the right step, and by how much — on
a held-out set of 12 test cases the team has not looked at yet. That
number is `{{P5_TEST}}`. On a smaller diagnostic set the team *did* look at
while building the tool, Bisect got the exact right answer whenever the
judge's shortlist even considered it, and said nothing when it wasn't
shortlisted — a promising early sign, reported as a diagnostic, not a
result.

**Worth knowing going in:** with only 18 real planted failures to test
against (versus a 120-item goal), the final comparison has limited power
to prove a modest advantage — even a real 15-point edge for Bisect might
not show up as statistically significant at this sample size. A strong
result would still be meaningful; a null result mostly means "we need more
data," not "the idea doesn't work." That's stated plainly in the final
report rather than glossed over.

---

## Tab 4 — Moving forward

**Immediate next step:** the test-split evaluation finishes, the headline
numbers get filled in everywhere they're currently marked `{{P5_TEST}}`,
and the final report is published with nothing left pending.

**What would make the evidence stronger, if there were more budget:**
- **More labelled failures.** The dataset came in at 18 rather than the
  120 originally aimed for, because a single planted mistake turns out to
  rarely break this particular agent. A bigger budget (or a less
  robust agent) would produce a bigger, more statistically decisive
  dataset.
- **The "does this help under real unpredictability" test wasn't fully
  collected.** The mechanism that justifies snapshots — that they hold up
  even when the world around the agent is genuinely unpredictable — was
  proven offline and deterministically (100% reproduction vs. 0%), but the
  live head-to-head version of that comparison only gathered 3 usable
  examples before running out of time, too few to draw a statistical
  conclusion from. It's reported as "not collected," not glossed over as a
  small result.
- **A refinement worth exploring**: pairing the "what if we fixed this
  step" run and the "what actually happened" comparison run so they share
  the same underlying randomness, which a recent paper argues gives a
  cleaner signal for isolating one step's true effect. Nothing here claims
  to have done this yet — it's flagged as a candidate improvement.

**Where this could go next.** The core engine was deliberately built so
the blame-finding logic knows nothing about the specific benchmark it was
tested on — the next project in this line reuses the recording and replay
layer as-is, aimed at a different kind of agent failure entirely.

---

## Tab 5 — Test it locally

No API key needed for the first three commands (`doctor` without `--live`,
`serve --fixture`, and `make reproduce` all run on synthetic or already-
recorded data).

```bash
# Install
uv tool install git+https://github.com/kidus-der/agent-bisect
cp .env.example .env          # then add your own NVIDIA_API_KEY to try live recording

# Check the install
bisect doctor                 # key, tool-calling, one demo task end to end (needs the key)

# See the dashboard without any API key, on a built-in simulated dataset
bisect serve --fixture

# See the dashboard against a real set of recorded runs (once you have some)
bisect serve --real

# Record a real agent run against a live model (needs the key)
bisect record --domain airline --tasks 0-19

# Rewind a recorded run and find out which step caused it to fail
bisect blame RUN_ID --top 3 --n 8

# Rebuild every number and figure in the final report, entirely offline,
# and verify it matches exactly what is committed
make reproduce
```

Everything under `make reproduce` reads only files already checked into
the repository — no API key, no network access, and it will refuse to
finish quietly if a number it recomputes doesn't match what's published.
