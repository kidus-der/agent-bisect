import { describe, expect, test } from 'vitest'

import type { InterventionDiff, RunEstimate } from '@/features/run-detail/api'

import type { RunSummary } from './api'
import { heroRewindSpec, interventionSummary, rerunsForStep, verdictForStep } from './heroRun'

const RUN: RunSummary = {
  run_id: 'brief-12-step',
  domain: 'airline',
  task_id: 'refund_after_cancellation',
  model: 'nvidia/llama-3.1-nemotron-70b-instruct',
  status: 'complete',
  outcome: 'fail',
  n_steps: 12,
  decisive_step: 7,
  fault_type: 'wrong_value',
  planted_step: 7,
  cost_usd: 0.97,
  calls: 470,
  sparkline: [],
  blame_stripe: [],
}

const ESTIMATE = {
  blamed_step: 7,
  control_mode: 'shared',
  control_fork_step: 1,
  treated_reruns: 16,
  control_reruns: 16,
  sampler_calls: 100,
  step_effects: [
    {
      step: 7,
      treated: { successes: 8, n: 8 },
      control: { successes: 2, n: 16 },
      effect: 0.875,
      ci_low: 0.4743,
      ci_high: 0.965,
      n_batches: 2,
      stop_reason: 'blameworthy',
    },
  ],
} as unknown as RunEstimate

const DIFF: InterventionDiff = {
  step_idx: 7,
  original_tool_result: { reservation_id: 'NM1VX1', status: 'confirmed', origin: 'JFK' },
  replaced_tool_result: { reservation_id: 'ZFA04Y', status: 'confirmed', origin: 'JFK' },
}

describe('interventionSummary', () => {
  test('names the one field the intervention changed and both of its values', () => {
    expect(interventionSummary(DIFF)).toEqual({
      field: 'reservation_id',
      before: 'NM1VX1',
      after: 'ZFA04Y',
    })
  })

  test('returns null when the API served no diff for the step', () => {
    expect(interventionSummary(null)).toBeNull()
  })

  test('returns null when nothing in the tool result actually differs', () => {
    expect(
      interventionSummary({ ...DIFF, replaced_tool_result: DIFF.original_tool_result }),
    ).toBeNull()
  })

  test('truncates a long value so it cannot break the tape layout', () => {
    const long = 'x'.repeat(80)
    const summary = interventionSummary({
      ...DIFF,
      replaced_tool_result: { ...DIFF.original_tool_result, reservation_id: long },
    })
    expect(summary?.after).toHaveLength(24)
    expect(summary?.after.endsWith('…')).toBe(true)
  })
})

describe('verdictForStep', () => {
  test('carries the measured effect with its interval', () => {
    expect(verdictForStep(ESTIMATE, 7)).toEqual({
      step: 7,
      effect: 0.875,
      low: 0.4743,
      high: 0.965,
    })
  })

  test('is null for a step that was never tested', () => {
    expect(verdictForStep(ESTIMATE, 4)).toBeNull()
    expect(verdictForStep(null, 7)).toBeNull()
  })
})

describe('rerunsForStep', () => {
  test('uses the treated arm size actually run at that step', () => {
    expect(rerunsForStep(ESTIMATE, 7)).toBe(8)
  })

  test('falls back to the run-level count for an untested step', () => {
    expect(rerunsForStep(ESTIMATE, 4)).toBe(16)
  })
})

describe('heroRewindSpec', () => {
  test('builds the spec from the run the API served', () => {
    expect(heroRewindSpec({ run: RUN, estimate: ESTIMATE, interventionDiff: DIFF })).toEqual({
      stepCount: 12,
      targetStep: 7,
      reruns: 8,
      intervention: { field: 'reservation_id', before: 'NM1VX1', after: 'ZFA04Y' },
      verdict: { step: 7, effect: 0.875, low: 0.4743, high: 0.965 },
    })
  })

  test('declines a run with no decisive step rather than inventing one', () => {
    const run: RunSummary = { ...RUN, decisive_step: null }
    expect(heroRewindSpec({ run, estimate: null, interventionDiff: null })).toBeNull()
  })

  test('declines a run whose blamed step is its last, since nothing would replay', () => {
    const run: RunSummary = { ...RUN, decisive_step: 12 }
    expect(heroRewindSpec({ run, estimate: ESTIMATE, interventionDiff: DIFF })).toBeNull()
  })

  test('still builds a spec when the estimate and the diff are missing', () => {
    const spec = heroRewindSpec({ run: RUN, estimate: null, interventionDiff: null })
    expect(spec).toMatchObject({ stepCount: 12, targetStep: 7, intervention: null, verdict: null })
  })
})
