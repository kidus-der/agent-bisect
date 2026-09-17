# 0011 — The flaky world, and how its reward is computed

- **Date:** 2026-09-17, written **before any flaky-world data is collected**
  (no flaky recording, no drift measurement and no P5 ablation number existed
  when this file was committed).
- **Status:** accepted.
- **Extends:** `docs/decisions/0010-replay-mechanism.md` (the two prefix modes),
  `docs/decisions/0001-preregistration.md` (the P5 gate: "Flaky world: the
  no-snapshot baseline is measurably worse (CI of the difference above 0)").

## Why there is a flaky world at all

τ²'s airline and retail tools are deterministic functions of the database.
`_get_new_reservation_id` picks from a fixed list (`HATHAT`, `HATHAU`,
`HATHAV`), `_get_datetime` returns a constant, and neither domain uses
`random`, the clock, the network or the filesystem. On such a world, serving a
recorded tool result from a snapshot and re-executing the tool live give the
same answer, so snapshots buy speed and nothing else.

That is exactly the wrong place to argue that snapshots are *necessary*. The
claim in `docs/brief/summary.md` §2 is about correctness under
non-determinism: "the no-snapshot baseline measurably drifts and Bisect
doesn't". The flaky world is the environment where that claim can be false,
so it is the environment where it has to be tested.

## What the flaky world changes

`adapters/tau2_flaky.py` wraps a live τ² `Environment` and its toolkit
instance. Three sources of non-determinism, all driven by one RNG **seeded per
run** and recorded in the run manifest and the dataset manifest:

1. **Generated identifiers are random per execution.** The toolkit's id
   generator is replaced, so `book_reservation` mints a fresh random id instead
   of the next entry of a fixed list. The id is generated *inside* the tool, so
   the database and the returned record agree with each other within a run.
2. **Some read answers are time-dependent.** A simulated clock advances by
   `clock_seconds` per tool execution. The stamped creation times move with it,
   and availability and price fields in *returned* read results drift with it
   (seats sell, fares move) without the database being edited — the world
   changed because time passed, not because anyone wrote to it.
3. **Occasional injected tool errors**, with probability `p_error` (default
   0.05). The decision is made **before** the tool runs and the tool is then
   not executed at all, so an injected error leaves the database untouched —
   which is what a real transient backend failure does, and what τ²'s own error
   path does (`Environment.get_response` catches the exception and makes no
   state change).

The wrapper is installed on the environment *before* the recorder or the
replayer wraps `get_response`, so the recorder records the flaky answers and a
`rerun_live` prefix reaches them. A `snapshot` prefix never calls the tool at
all, which is the whole point.

## The consequence that forced this decision

**τ²'s evaluator re-executes the trajectory's write actions on an environment
of its own.** `EnvEvaluator` builds a fresh database, replays the run's write
actions against it and compares database hashes
(`evaluator/evaluator_env.py`; see `0010` §"The evaluator"). Under random
identifiers that comparison can never succeed:

- the evaluator's environment is a different instance, so it does not carry the
  flaky patches at all, and its `book_reservation` mints `HATHAT` while the run
  under test minted something random;
- even if it did carry them, its RNG draws would be a different sequence, so it
  would mint a *different* random id;
- the identifier is a dictionary **key** in `db.reservations`, so a single
  difference changes the whole database hash.

Measured, not assumed: recording a flaky run that books a flight and then
scoring it with `EvaluationType.ALL` does not merely return 0 — it **raises**.
`Environment.set_state` replays the write action, sees `HATHAT` where the
recording holds a random id, and raises `ValueError` under its strict replay
(`vendor/tau2-bench/src/tau2/environment/environment.py:399-402`). There is no
reward to report at all.

Every flaky run that writes anything would therefore fail to score, for a
reason that has nothing to do with the agent. Scoring an environment artefact
as an agent failure is exactly what `docs/decisions/0004-p0-probe-protocol.md`
§3 forbids, and it would make the flaky-world arm unusable as evidence for or
against snapshots.

τ² cannot be made consistent here without changing τ², which
`docs/decisions/0003-tau2-pin.md` pins precisely so that it is not changed.

## The decision

**In the flaky world, the reward is the DB-state check against the recorded
golden actions, computed on a canonicalised database.** Concretely:

1. The flaky world records the ordered trail of identifiers it generated and
   the clock stamps it issued, per run.
2. `canonical_ids(trail)` maps the *i*-th generated identifier to the *i*-th
   identifier the deterministic domain would have produced, and every issued
   clock stamp to the domain's fixed base timestamp.
3. Before hashing, that mapping is applied throughout the database dump — to
   dictionary **keys** and to string **values**, at any depth — and to the tool
   arguments of the golden actions being replayed.
4. The reward is then τ²'s own comparison, unchanged, over the canonicalised
   hashes: `get_dict_hash` with `sort_keys=True`, as in
   `tau2.utils.utils.get_dict_hash`.

Canonicalisation is a **renaming**, not a relaxation. Two databases that differ
in anything other than which random name an identifier got still hash
differently: the number of reservations, which user they belong to, their
flights, cabins, prices and baggage counts are all compared exactly as before.
A run that books the wrong flight still fails; a run that books the right
flight under a random name still passes.

### What this does not cover, and what is done instead

- **Non-deterministic tool *content*** (drifting availability and prices) is
  not canonicalised, because it is not a naming artefact — it is a genuine
  difference in what the world said. Drifting fields are therefore confined to
  values the DB check does not read: they appear in returned read results and
  never in the stored database.
- **Injected errors** need no special treatment: they change the trajectory,
  not the naming, and an agent that fails to recover from a transient error has
  genuinely failed.

## Reported consequences

- The flaky-world reward is **not** τ²'s stock reward, and every number
  produced under it must say so. `docs/gates/P3.md` and the P5 ablation both
  label the arm explicitly.
- Plain-world numbers are unaffected: nothing in this decision changes how a
  deterministic airline or retail run is scored, and the P3 dataset itself is
  collected in the plain world.
- The drift rate measured in `rerun_live` versus `snapshot` mode is reported
  with the P3 evidence, as the fact that justifies the engine.
