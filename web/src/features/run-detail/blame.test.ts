import { describe, expect, it } from 'vitest'

import type { StepEffect } from './api'
import { DELTA, blameVerdict, clearsDelta, earliestClearingStep, heatCells, judgeMissed } from './blame'

function effect(step: number, value: number, low: number, high: number): StepEffect {
  return {
    step,
    effect: value,
    ci_low: low,
    ci_high: high,
    n_batches: 4,
    stop_reason: 'max_n',
    treated: { successes: 1, n: 16 },
    control: { successes: 1, n: 16 },
  }
}

describe('clearsDelta', () => {
  it('needs the interval lower bound strictly above delta, not the estimate', () => {
    // A big estimate whose interval still touches delta is not blame.
    expect(clearsDelta(effect(3, 0.9, 0.05, 0.99), DELTA)).toBe(false)
    expect(clearsDelta(effect(3, 0.4, 0.11, 0.7), DELTA)).toBe(true)
  })
})

describe('earliestClearingStep', () => {
  it('blames the earliest clearing step, not the largest effect', () => {
    // Arrange: step 9 has the bigger effect, step 4 clears first.
    const effects = [
      effect(4, 0.4, 0.2, 0.6),
      effect(9, 0.8, 0.5, 0.95),
      effect(2, 0.05, -0.2, 0.3),
    ]

    // Act
    const blamed = earliestClearingStep(effects, DELTA)

    // Assert
    expect(blamed).toBe(4)
  })

  it('returns null when no step clears delta', () => {
    expect(earliestClearingStep([effect(1, 0.2, -0.1, 0.5)], DELTA)).toBeNull()
  })

  it('returns null for a run with no tested steps', () => {
    expect(earliestClearingStep([], DELTA)).toBeNull()
  })
})

describe('blameVerdict', () => {
  it("prefers the server's blamed step and carries its interval", () => {
    const effects = [effect(7, 0.875, 0.4743, 0.965)]

    const verdict = blameVerdict({ blamed_step: 7, step_effects: effects })

    expect(verdict).toEqual({ step: 7, effect: 0.875, low: 0.4743, high: 0.965 })
  })

  it('is null when the server blamed nothing', () => {
    expect(blameVerdict({ blamed_step: null, step_effects: [] })).toBeNull()
  })

  it('is null when the blamed step has no effect row to show with it', () => {
    expect(blameVerdict({ blamed_step: 7, step_effects: [effect(3, 0.4, 0.2, 0.6)] })).toBeNull()
  })
})

describe('heatCells', () => {
  it('marks untested steps as untested instead of giving them an effect', () => {
    // Arrange
    const effects = [effect(2, 0.3, 0.15, 0.5)]

    // Act
    const cells = heatCells(3, effects)

    // Assert
    expect(cells).toEqual([
      { step: 1, effect: null, low: null, high: null, tested: false },
      { step: 2, effect: 0.3, low: 0.15, high: 0.5, tested: true },
      { step: 3, effect: null, low: null, high: null, tested: false },
    ])
  })
})

describe('judgeMissed', () => {
  it('is true when the judge never ranked the decisive step', () => {
    const ranking = [{ step: 3, rank: 1, score: 0.8, rationale: 'x' }]
    expect(judgeMissed(ranking, 7)).toBe(true)
  })

  it('is false when the judge ranked it anywhere', () => {
    const ranking = [
      { step: 3, rank: 1, score: 0.8, rationale: 'x' },
      { step: 7, rank: 2, score: 0.2, rationale: 'y' },
    ]
    expect(judgeMissed(ranking, 7)).toBe(false)
  })

  it('is false when there is no decisive step to miss', () => {
    expect(judgeMissed([], null)).toBe(false)
  })
})
