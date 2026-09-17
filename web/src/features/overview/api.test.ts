import { describe, expect, test } from 'vitest'

import { type OverviewPayload, accuracyIntervals, isOverviewPayload, methodLabel } from './api'

const PAYLOAD: OverviewPayload = {
  headline: {
    bisect: { value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 },
    best_judge: { value: 0.8721, ci_low: 0.7853, ci_high: 0.9271 },
    best_judge_method: 'judge_step_by_step',
    gap: { value: 0.1512, ci_low: 0.0581, ci_high: 0.2442 },
  },
  kpis: {
    runs_recorded: 266,
    failures_diagnosed: 86,
    calls_spent: 86490,
    cost_per_diagnosis_usd: 1.5209,
  },
  recall_at_m: [{ m: 1, recall: 0.7674 }],
  cost_vs_accuracy: [{ method: 'bisect', mean_cost_usd: 1.5607, accuracy: 0.9651 }],
  hero_run: {
    run_id: 'brief-12-step',
    domain: 'airline',
    task_id: 'refund_after_cancellation',
    model: 'm',
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
  },
}

describe('isOverviewPayload', () => {
  test('accepts the payload the API contract describes', () => {
    expect(isOverviewPayload(PAYLOAD)).toBe(true)
  })

  test('rejects a different endpoint’s payload served by mistake', () => {
    expect(isOverviewPayload({ data_source: 'fixture', simulated: true })).toBe(false)
  })

  test('rejects a headline with no interval for the gap', () => {
    const { gap: _gap, ...headline } = PAYLOAD.headline
    expect(isOverviewPayload({ ...PAYLOAD, headline })).toBe(false)
  })

  test('rejects a payload missing the pieces the page draws', () => {
    const { hero_run: _heroRun, ...withoutHero } = PAYLOAD
    expect(isOverviewPayload(withoutHero)).toBe(false)
    expect(isOverviewPayload({ ...PAYLOAD, recall_at_m: null })).toBe(false)
  })

  test('rejects nullish and primitive values', () => {
    expect(isOverviewPayload(null)).toBe(false)
    expect(isOverviewPayload(undefined)).toBe(false)
    expect(isOverviewPayload('overview')).toBe(false)
  })
})

describe('accuracyIntervals', () => {
  test('is empty when the benchmark request produced nothing', () => {
    expect(accuracyIntervals(null).size).toBe(0)
  })
})

describe('methodLabel', () => {
  test('gives every method a human name', () => {
    expect(methodLabel('judge_all_at_once')).toBe('Judge · all at once')
    expect(methodLabel('no_control')).toBe('No control')
  })
})
