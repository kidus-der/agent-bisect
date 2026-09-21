# The NIM rate limit is token-based, and P0 measured it in the wrong unit

- **Date:** 2026-09-20, measured during P5's test split after throughput collapsed.
- **Affects:** `config/limits.toml`, every phase's throughput planning, and P8's account of
  why P5 is incomplete.

## The measurement

All bursts against `nvidia/nemotron-3-super-120b-a12b` with the evaluation stopped, so we
contributed no other load. Limiter set to 60 rpm, i.e. barely engaged.

| burst | prompt size | output cap | result |
|---|---|---|---|
| 1 call | trivial | 8 | **1/1 ok**, 2.4 s |
| 4 concurrent | trivial | 8 | **4/4 ok**, 0.8–3.2 s |
| 8 concurrent | trivial | 8 | **8/8 ok** |
| 8 concurrent | ~2,500 tokens | 300 | **1/8 ok** |
| 2 concurrent | ~2,500 tokens | 300 | 2/2 ok, 12–55 s |
| 4 concurrent | ~2,500 tokens | 300 | 4/4 ok, **14–167 s** |
| the P5 evaluation, 12 in flight | real τ² conversations | — | **92% of calls retrying** |

Eight concurrent *small* requests succeed. Eight concurrent *large* ones, at the same
moment and the same request rate, fail seven times out of eight. The variable that moves
is tokens, not requests.

**Tokens are not the only variable.** P3's collection ran at 100+ calls/min with the same
τ² payloads earlier the same day, and P5 itself sustained 110 calls/min at 17:30, so the
ceiling also moves with load on the provider's side — capacity we neither see nor control.
The honest statement is that the limit is token-shaped *and* time-varying: our
`requests_per_minute` constant is the wrong unit, and no constant in the right unit would
have been right all day either.

## Why this matters beyond P5

`config/limits.toml` says 108 requests/min for this model, "measured … minus a 10% safety
margin", and its header says not to hand-tune it. That number is sound for the traffic P0
used to measure it — the ramp in `docs/decisions/0004-p0-probe-protocol.md` sends small
probe requests. It is the wrong unit for τ² traffic, where one agent turn carries a whole
conversation and one judge call carries an entire trajectory.

So the limiter can be comfortably inside its configured rate while the account is far past
its actual ceiling, which is exactly what P5 observed: 110 calls/min sustained at 17:30,
then a 429 storm in which 1,546 of 1,549 agent calls were retries, with the limiter never
binding.

**Every throughput number planned against `requests_per_minute` in this project is
therefore optimistic by an unknown factor** that depends on payload size. P5's own
projections (`docs/findings/p5-cost.md`) are built on calls per fork and are correct as
counts, but the wall-clock estimates derived from them are not.

## What was not done about it

The limiter was **not** re-tuned. `config/limits.toml` carries P0's measured evidence and
says to re-measure rather than hand-edit, and a proper re-measurement is a token-based ramp
that nobody has run. Lowering the number by guesswork would replace one wrongly-calibrated
constant with another, and would also change a pinned input mid-phase.

What P5 did instead was stop spending: an evaluation that is 92% retries is buying nothing,
and every retry is its own ledger row against the 80,000-call cap.

## Recommendation

1. Re-measure the ceiling in **tokens per minute**, with realistic payloads, and express
   `config/limits.toml` in those terms — or keep requests/min but calibrate it at the
   payload size the phase actually sends.
2. Until then, treat 2–4 concurrent large requests as the working assumption for τ²
   traffic, and expect 1–3 minute latencies at the upper end.
3. P8 should report this as a measurement error in our own instrumentation, not as a
   provider fault. The provider behaved consistently; we were measuring the wrong thing.
