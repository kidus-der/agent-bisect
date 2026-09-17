/**
 * The rewind sequence as data: a pure list of frames. The component only plays
 * them, so the sequence is unit-testable and reduced motion can jump to the
 * final frame.
 *
 * A spec describes one real run (step count, the step blamed, the intervention
 * and the measured effect), so the same player drives both the gallery's
 * illustration and the Overview's hero, which is a run the API actually served.
 */
import type { TapeStepState } from '@/components/primitives/TapeStep'

export const REWIND_STEP_COUNT = 12
export const REWIND_TARGET_STEP = 7
export const REWIND_RERUNS = 8

export const REWIND_INTERVENTION = { field: null, before: 'NM1VX1', after: 'ZFA04Y' } as const
export const REWIND_VERDICT = {
  step: REWIND_TARGET_STEP,
  effect: 0.75,
  low: 0.41,
  high: 0.94,
} as const

export interface RewindIntervention {
  /** The tool-result field that was replaced, when the diff names one. */
  readonly field: string | null
  readonly before: string
  readonly after: string
}

export interface RewindVerdict {
  readonly step: number
  readonly effect: number
  readonly low: number
  readonly high: number
}

export interface RewindSpec {
  readonly stepCount: number
  /** 1-based step the run is rewound to. */
  readonly targetStep: number
  /** How many times the tail was re-run per arm. */
  readonly reruns: number
  /** Null when the API served no intervention diff for this step. */
  readonly intervention: RewindIntervention | null
  /** Null when no effect was measured; blame is then never shown with a number. */
  readonly verdict: RewindVerdict | null
}

export const DEFAULT_REWIND_SPEC: RewindSpec = {
  stepCount: REWIND_STEP_COUNT,
  targetStep: REWIND_TARGET_STEP,
  reruns: REWIND_RERUNS,
  intervention: REWIND_INTERVENTION,
  verdict: REWIND_VERDICT,
}

export type RewindPhase = 'record' | 'fail' | 'rewind' | 'intervene' | 'replay' | 'pass' | 'verdict'

export interface RewindFrame {
  readonly phase: RewindPhase
  /** State of each step, index 0 = step 1. */
  readonly steps: readonly TapeStepState[]
  /** 1-based step the playhead sits on. */
  readonly playhead: number
  /** How many leading steps have already been returned to tape. Drives the sweep. */
  readonly rewoundThrough: number
  readonly status: string
  readonly holdMs: number
  readonly showTapeBand: boolean
  readonly showIntervention: boolean
  readonly showRerunBand: boolean
}

const HOLD_MS = {
  fail: 1100,
  rewindStep: 55,
  rewindSettle: 900,
  intervene: 1500,
  replayStep: 300,
  pass: 1100,
  verdict: 3200,
} as const

/** A long run should not spend ten seconds recording; the whole pass is budgeted instead. */
const RECORD_BUDGET_MS = 2040
const RECORD_STEP_MIN_MS = 60
const RECORD_STEP_MAX_MS = 170

function recordHoldMs(stepCount: number): number {
  const perStep = Math.round(RECORD_BUDGET_MS / Math.max(stepCount, 1))
  return Math.min(RECORD_STEP_MAX_MS, Math.max(RECORD_STEP_MIN_MS, perStep))
}

function stepNumbers(stepCount: number): readonly number[] {
  return Array.from({ length: stepCount }, (_, index) => index + 1)
}

function interventionText(intervention: RewindIntervention | null): string {
  if (!intervention) return 'tool result replaced'
  const field = intervention.field ? `${intervention.field} ` : ''
  return `tool result replaced · ${field}${intervention.before} → ${intervention.after}`
}

interface Builder {
  readonly spec: RewindSpec
  readonly steps: readonly number[]
  readonly recordMs: number
}

function stepsFrom(
  builder: Builder,
  stateOf: (step: number) => TapeStepState,
): readonly TapeStepState[] {
  return builder.steps.map(stateOf)
}

/** After the rewind: 1..k-1 come from tape, k is the intervention, the rest depend on `tail`. */
function replayedSteps(
  builder: Builder,
  tail: (step: number) => TapeStepState,
): readonly TapeStepState[] {
  const { targetStep } = builder.spec
  return stepsFrom(builder, (step) => {
    if (step < targetStep) return 'tape'
    if (step === targetStep) return 'blamed'
    return tail(step)
  })
}

const NO_BANDS = { showTapeBand: false, showIntervention: false, showRerunBand: false } as const

function recordFrames(builder: Builder): readonly RewindFrame[] {
  const { stepCount } = builder.spec
  return builder.steps.map((current) => ({
    phase: 'record' as const,
    steps: stepsFrom(builder, (step) =>
      step < current ? 'ran' : step === current ? 'live' : 'pending',
    ),
    playhead: current,
    rewoundThrough: 0,
    status: `recording live · step ${current} of ${stepCount}`,
    holdMs: builder.recordMs,
    ...NO_BANDS,
  }))
}

/**
 * The sweep: one frame per step returned to tape, left to right, so the leading
 * run visibly desaturates instead of snapping to its final state.
 */
function rewindFrames(builder: Builder): readonly RewindFrame[] {
  const { targetStep, stepCount } = builder.spec
  const rewound = builder.steps.filter((step) => step < targetStep)
  return rewound.map((boundary, index) => {
    const last = index === rewound.length - 1
    return {
      phase: 'rewind' as const,
      steps: stepsFrom(builder, (step) => {
        if (step <= boundary) return 'tape'
        if (step <= targetStep) return 'ran'
        return last ? 'pending' : 'ran'
      }),
      playhead: targetStep,
      rewoundThrough: boundary,
      status: last
        ? `rewind to step ${targetStep} · steps 1–${targetStep - 1} read from tape · 0 calls`
        : `rewinding · step ${boundary} of ${stepCount} back to tape`,
      holdMs: last ? HOLD_MS.rewindSettle : HOLD_MS.rewindStep,
      ...NO_BANDS,
      showTapeBand: last,
    }
  })
}

function replayFrames(builder: Builder): readonly RewindFrame[] {
  const { targetStep, stepCount, reruns } = builder.spec
  return builder.steps
    .filter((step) => step > targetStep)
    .map((current) => ({
      phase: 'replay' as const,
      steps: replayedSteps(builder, (step) =>
        step < current ? 'ran' : step === current ? 'live' : 'pending',
      ),
      playhead: current,
      rewoundThrough: targetStep - 1,
      status: `re-run live × ${reruns} · step ${current} of ${stepCount}`,
      holdMs: HOLD_MS.replayStep,
      showTapeBand: true,
      showIntervention: true,
      showRerunBand: true,
    }))
}

export function buildRewindFrames(spec: RewindSpec = DEFAULT_REWIND_SPEC): readonly RewindFrame[] {
  const builder: Builder = {
    spec,
    steps: stepNumbers(spec.stepCount),
    recordMs: recordHoldMs(spec.stepCount),
  }
  const { stepCount, targetStep } = spec
  const failed = stepsFrom(builder, (step) => (step === stepCount ? 'failed' : 'ran'))
  const replayDone = replayedSteps(builder, (step) => (step === stepCount ? 'passed' : 'ran'))
  const afterRewind = { showTapeBand: true, showIntervention: true, showRerunBand: true } as const

  return [
    ...recordFrames(builder),
    {
      phase: 'fail',
      steps: failed,
      playhead: stepCount,
      rewoundThrough: 0,
      status: `✕ fail at step ${stepCount}`,
      holdMs: HOLD_MS.fail,
      ...NO_BANDS,
    },
    ...rewindFrames(builder),
    {
      phase: 'intervene',
      steps: replayedSteps(builder, () => 'pending'),
      playhead: targetStep,
      rewoundThrough: targetStep - 1,
      status: `step ${targetStep} · ${interventionText(spec.intervention)}`,
      holdMs: HOLD_MS.intervene,
      showTapeBand: true,
      showIntervention: true,
      showRerunBand: false,
    },
    ...replayFrames(builder),
    {
      phase: 'pass',
      steps: replayDone,
      playhead: stepCount,
      rewoundThrough: targetStep - 1,
      status: '✓ pass',
      holdMs: HOLD_MS.pass,
      ...afterRewind,
    },
    {
      phase: 'verdict',
      steps: replayDone,
      playhead: stepCount,
      rewoundThrough: targetStep - 1,
      status: `blame: step ${targetStep}`,
      holdMs: HOLD_MS.verdict,
      ...afterRewind,
    },
  ]
}
