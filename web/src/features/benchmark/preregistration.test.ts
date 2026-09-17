import { describe, expect, test } from 'vitest'

import type { MethodResult } from './api'
import { PREREGISTERED_MARGIN, preregisteredBar } from './preregistration'

function method(name: MethodResult['method'], value: number): MethodResult {
  return {
    method: name,
    accuracy: { value, ci_low: value - 0.05, ci_high: Math.min(1, value + 0.05) },
    mean_cost_usd: 1,
    mean_calls: 10,
  }
}

describe('preregisteredBar', () => {
  test('sets the bar at the best judge plus the pre-registered margin', () => {
    // Arrange
    const methods = [
      method('bisect', 0.9),
      method('judge_all_at_once', 0.6),
      method('judge_step_by_step', 0.7),
    ]

    // Act
    const bar = preregisteredBar(methods)

    // Assert
    expect(bar?.bestJudge.method).toBe('judge_step_by_step')
    expect(bar?.threshold).toBeCloseTo(0.7 + PREREGISTERED_MARGIN, 6)
  })

  test('reports the bar as cleared when Bisect reaches it', () => {
    // Arrange / Act
    const bar = preregisteredBar([method('bisect', 0.9), method('judge_step_by_step', 0.7)])

    // Assert
    expect(bar?.cleared).toBe(true)
    expect(bar?.unattainable).toBe(false)
  })

  test('flags a bar that sits above the maximum attainable accuracy', () => {
    // Arrange — the fixture's best judge is 0.8721, so the bar is 1.0221.
    const bar = preregisteredBar([method('bisect', 0.9651), method('judge_step_by_step', 0.8721)])

    // Assert
    expect(bar?.threshold).toBeGreaterThan(1)
    expect(bar?.unattainable).toBe(true)
    expect(bar?.cleared).toBe(false)
  })

  test('reports the margin Bisect actually holds over the best judge', () => {
    // Arrange / Act
    const bar = preregisteredBar([method('bisect', 0.9651), method('judge_step_by_step', 0.8721)])

    // Assert
    expect(bar?.marginOverBestJudge).toBeCloseTo(0.093, 4)
  })

  test('returns null when no judge method was evaluated', () => {
    expect(preregisteredBar([method('bisect', 0.9)])).toBeNull()
  })

  test('returns null when Bisect itself was not evaluated', () => {
    expect(preregisteredBar([method('judge_step_by_step', 0.7)])).toBeNull()
  })
})
