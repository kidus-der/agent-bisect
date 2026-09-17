/**
 * The rewind illustration as data: a pure list of frames. The component only
 * plays them, so the sequence is unit-testable and reduced motion can jump to
 * the final frame.
 */
import type { TapeStepState } from '@/components/primitives/TapeStep'

export const REWIND_STEP_COUNT = 12
export const REWIND_TARGET_STEP = 7
export const REWIND_RERUNS = 8

export const REWIND_INTERVENTION = { before: 'NM1VX1', after: 'ZFA04Y' } as const
export const REWIND_VERDICT = {
  step: REWIND_TARGET_STEP,
  effect: 0.75,
  low: 0.41,
  high: 0.94,
} as const

export type RewindPhase = 'record' | 'fail' | 'rewind' | 'intervene' | 'replay' | 'pass' | 'verdict'

export interface RewindFrame {
  readonly phase: RewindPhase
  /** State of each step, index 0 = step 1. */
  readonly steps: readonly TapeStepState[]
  /** 1-based step the playhead sits on. */
  readonly playhead: number
  readonly status: string
  readonly holdMs: number
  readonly showTapeBand: boolean
  readonly showIntervention: boolean
  readonly showRerunBand: boolean
}

const HOLD_MS = {
  recordStep: 170,
  fail: 1100,
  rewind: 1300,
  intervene: 1500,
  replayStep: 300,
  pass: 1100,
  verdict: 3200,
} as const

const STEP_NUMBERS: readonly number[] = Array.from(
  { length: REWIND_STEP_COUNT },
  (_, index) => index + 1,
)

function stepsFrom(stateOf: (step: number) => TapeStepState): readonly TapeStepState[] {
  return STEP_NUMBERS.map(stateOf)
}

/** After the rewind: 1..k-1 come from tape, k is the intervention, the rest depend on `tail`. */
function replayedSteps(tail: (step: number) => TapeStepState): readonly TapeStepState[] {
  return stepsFrom((step) => {
    if (step < REWIND_TARGET_STEP) return 'tape'
    if (step === REWIND_TARGET_STEP) return 'blamed'
    return tail(step)
  })
}

const NO_BANDS = { showTapeBand: false, showIntervention: false, showRerunBand: false } as const

function recordFrames(): readonly RewindFrame[] {
  return STEP_NUMBERS.map((current) => ({
    phase: 'record' as const,
    steps: stepsFrom((step) => (step < current ? 'ran' : step === current ? 'live' : 'pending')),
    playhead: current,
    status: `recording live · step ${current} of ${REWIND_STEP_COUNT}`,
    holdMs: HOLD_MS.recordStep,
    ...NO_BANDS,
  }))
}

function replayFrames(): readonly RewindFrame[] {
  return STEP_NUMBERS.filter((step) => step > REWIND_TARGET_STEP).map((current) => ({
    phase: 'replay' as const,
    steps: replayedSteps((step) =>
      step < current ? 'ran' : step === current ? 'live' : 'pending',
    ),
    playhead: current,
    status: `re-run live × ${REWIND_RERUNS} · step ${current} of ${REWIND_STEP_COUNT}`,
    holdMs: HOLD_MS.replayStep,
    showTapeBand: true,
    showIntervention: true,
    showRerunBand: true,
  }))
}

export function buildRewindFrames(): readonly RewindFrame[] {
  const failed = stepsFrom((step) => (step === REWIND_STEP_COUNT ? 'failed' : 'ran'))
  const replayDone = replayedSteps((step) => (step === REWIND_STEP_COUNT ? 'passed' : 'ran'))
  return [
    ...recordFrames(),
    {
      phase: 'fail',
      steps: failed,
      playhead: REWIND_STEP_COUNT,
      status: `✕ fail at step ${REWIND_STEP_COUNT}`,
      holdMs: HOLD_MS.fail,
      ...NO_BANDS,
    },
    {
      phase: 'rewind',
      steps: stepsFrom((step) =>
        step < REWIND_TARGET_STEP ? 'tape' : step === REWIND_TARGET_STEP ? 'ran' : 'pending',
      ),
      playhead: REWIND_TARGET_STEP,
      status: `rewind to step ${REWIND_TARGET_STEP} · steps 1–${REWIND_TARGET_STEP - 1} read from tape · 0 calls`,
      holdMs: HOLD_MS.rewind,
      ...NO_BANDS,
      showTapeBand: true,
    },
    {
      phase: 'intervene',
      steps: replayedSteps(() => 'pending'),
      playhead: REWIND_TARGET_STEP,
      status: `step ${REWIND_TARGET_STEP} · tool result replaced · ${REWIND_INTERVENTION.before} → ${REWIND_INTERVENTION.after}`,
      holdMs: HOLD_MS.intervene,
      showTapeBand: true,
      showIntervention: true,
      showRerunBand: false,
    },
    ...replayFrames(),
    {
      phase: 'pass',
      steps: replayDone,
      playhead: REWIND_STEP_COUNT,
      status: '✓ pass',
      holdMs: HOLD_MS.pass,
      showTapeBand: true,
      showIntervention: true,
      showRerunBand: true,
    },
    {
      phase: 'verdict',
      steps: replayDone,
      playhead: REWIND_STEP_COUNT,
      status: `blame: step ${REWIND_VERDICT.step}`,
      holdMs: HOLD_MS.verdict,
      showTapeBand: true,
      showIntervention: true,
      showRerunBand: true,
    },
  ]
}
