import { describe, expect, test } from 'vitest'

import type { PrCheckSummary } from './api'
import { buildGateSummary, checkDelta, deltaAxisBound } from './gateSummary'

function check(overrides: Partial<PrCheckSummary> = {}): PrCheckSummary {
  return {
    check_id: 'pr-check-00',
    pr_number: 1000,
    title: 'reschedule_flight_change',
    is_regression: true,
    base_pass_rate: 0.875,
    head_pass_rate: 0.5833,
    p_value: 0.023,
    ...overrides,
  }
}

const CHECKS: readonly PrCheckSummary[] = [
  check(),
  check({
    check_id: 'pr-check-01',
    pr_number: 1001,
    base_pass_rate: 0.9167,
    head_pass_rate: 0.625,
  }),
  check({
    check_id: 'pr-check-03',
    pr_number: 1003,
    is_regression: false,
    base_pass_rate: 0.79,
    head_pass_rate: 0.83,
  }),
  check({
    check_id: 'pr-check-04',
    pr_number: 1004,
    is_regression: false,
    base_pass_rate: 0.75,
    head_pass_rate: 0.75,
  }),
]

describe('checkDelta', () => {
  test('carries the change and its interval', () => {
    // Act
    const delta = checkDelta(check())

    // Assert
    expect(delta.delta).toBeCloseTo(-0.2917, 4)
    expect(delta.interval).not.toBeNull()
    expect(delta.interval?.high).toBeLessThan(0)
  })

  test('calls a change decisive only when its interval excludes zero', () => {
    expect(checkDelta(check()).decisive).toBe(true)
    expect(checkDelta(CHECKS[2] as PrCheckSummary).decisive).toBe(false)
    expect(checkDelta(CHECKS[3] as PrCheckSummary).decisive).toBe(false)
  })
})

describe('buildGateSummary', () => {
  test('counts the verdicts the server gave', () => {
    // Act
    const summary = buildGateSummary(CHECKS)

    // Assert
    expect(summary.regressions).toBe(2)
    expect(summary.clean).toBe(2)
  })

  test('takes the median change, not the mean', () => {
    // Arrange — sorted the deltas are −0.2917, −0.2917, 0, +0.04, so the
    // middle two average −0.1459. A mean (−0.1359) is dragged by the two drops.
    const summary = buildGateSummary(CHECKS)

    // Assert
    expect(summary.medianDelta).toBeCloseTo(-0.14585, 4)
  })

  test('reports the worst and best single check for the axis', () => {
    const summary = buildGateSummary(CHECKS)
    expect(summary.worstDelta).toBeCloseTo(-0.2917, 4)
    expect(summary.bestDelta).toBeCloseTo(0.04, 4)
  })

  test('counts only the changes an interval separates from zero', () => {
    expect(buildGateSummary(CHECKS).decisiveCount).toBe(2)
  })

  test('is safe on an empty gate history', () => {
    // Act
    const summary = buildGateSummary([])

    // Assert — zeros, not NaN, and nothing invented.
    expect(summary).toMatchObject({
      regressions: 0,
      clean: 0,
      medianDelta: 0,
      worstDelta: 0,
      bestDelta: 0,
      decisiveCount: 0,
    })
    expect(summary.deltas).toEqual([])
  })
})

describe('deltaAxisBound', () => {
  test('is symmetric around zero at the widest change', () => {
    expect(deltaAxisBound(buildGateSummary(CHECKS))).toBeCloseTo(0.2917, 4)
  })

  test('never collapses to zero width', () => {
    expect(deltaAxisBound(buildGateSummary([]))).toBe(1)
  })
})
