/**
 * What every cell of the tape looks like, as pure data. The timeline only draws
 * the result, so the rewind sequence is unit-testable and reduced motion can
 * jump straight to the settled state.
 */
import type { TapeStepState } from '@/components/primitives/TapeStep'

export type RewindPhase = 'rewinding' | 'intervened' | 'replaying' | 'settled'

export interface RewindState {
  /** 1-based step the run was rewound to. */
  readonly step: number
  readonly phase: RewindPhase
  /** Last step of the tail that has re-played. Equals `step` before the tail starts. */
  readonly replayedThrough: number
  /** Outcome of the recorded treated re-run, once known. Never guessed. */
  readonly passed: boolean | null
  /**
   * How far the from-tape band has advanced during `rewinding`. Flipping a
   * 54-step prefix in one commit costs a dropped frame, so it moves in slices.
   */
  readonly bandedThrough: number
}

/** Number of commits the band is spread over, whatever the prefix length. */
const BAND_CHUNKS = 6

function bandChunk(step: number): number {
  return Math.max(1, Math.ceil((step - 1) / BAND_CHUNKS))
}

export interface TapeModel {
  readonly nSteps: number
  /** 1-based playhead. */
  readonly playhead: number
  readonly outcome: 'pass' | 'fail' | null
  /** The step blame landed on, marked on the tape before any rewind is played. */
  readonly blamedStep: number | null
  readonly rewind: RewindState | null
}

function outcomeState(passed: boolean | null): TapeStepState {
  if (passed === null) return 'ran'
  return passed ? 'passed' : 'failed'
}

/**
 * A recorded run: every step really did run, so none of them is "pending". The
 * playhead marks how far the replay has been scrubbed; the timeline dims what
 * lies after it rather than pretending it never happened.
 */
function recordedStates(model: TapeModel): readonly TapeStepState[] {
  const last = model.nSteps
  return Array.from({ length: model.nSteps }, (_, index) => {
    const step = index + 1
    if (step === model.blamedStep) return 'blamed'
    if (step !== last) return 'ran'
    return outcomeState(model.outcome === null ? null : model.outcome === 'pass')
  })
}

function rewoundStates(model: TapeModel, rewind: RewindState): readonly TapeStepState[] {
  const last = model.nSteps
  const leadingEdge = rewind.phase === 'replaying' ? rewind.replayedThrough + 1 : 0
  // The band only claims the prefix it has actually reached while it is moving.
  const banded = rewind.phase === 'rewinding' ? rewind.bandedThrough : rewind.step - 1
  return Array.from({ length: model.nSteps }, (_, index) => {
    const step = index + 1
    if (step < rewind.step) return step <= banded ? 'tape' : 'ran'
    if (step === rewind.step) return rewind.phase === 'rewinding' ? 'ran' : 'blamed'
    if (step === leadingEdge) return 'live'
    if (step > rewind.replayedThrough) return 'pending'
    if (step === last && rewind.phase === 'settled') return outcomeState(rewind.passed)
    return 'ran'
  })
}

export function tapeStepStates(model: TapeModel): readonly TapeStepState[] {
  return model.rewind ? rewoundStates(model, model.rewind) : recordedStates(model)
}

/** One tick of the rewind sequence. Terminal state returns itself, so the caller can stop. */
export function nextRewind(rewind: RewindState, nSteps: number): RewindState {
  if (rewind.phase === 'settled') return rewind
  if (rewind.phase === 'rewinding') {
    const bandedThrough = rewind.bandedThrough + bandChunk(rewind.step)
    if (bandedThrough >= rewind.step - 1) {
      return { ...rewind, phase: 'intervened', bandedThrough: rewind.step - 1 }
    }
    return { ...rewind, bandedThrough }
  }
  if (rewind.replayedThrough >= nSteps) return { ...rewind, phase: 'settled' }
  return { ...rewind, phase: 'replaying', replayedThrough: rewind.replayedThrough + 1 }
}

export function isRewindDone(rewind: RewindState | null): boolean {
  return rewind !== null && rewind.phase === 'settled'
}
