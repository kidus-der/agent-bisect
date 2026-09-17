import { describe, expect, test } from 'vitest'

import {
  FOREST_DOT_LAG_SECONDS,
  forestDotMotion,
  forestRowDelay,
  forestWhiskerMotion,
} from './forestEntrance'
import { STAGGER_SECONDS } from './motion'

describe('forestRowDelay', () => {
  test('staggers rows top to bottom', () => {
    expect(forestRowDelay({ index: 0, total: 6, reduced: false })).toBe(0)
    expect(forestRowDelay({ index: 2, total: 6, reduced: false })).toBeCloseTo(
      2 * STAGGER_SECONDS.forest,
      6,
    )
  })

  test('sends the deferred row in after every other, wherever it sits', () => {
    // Arrange / Act — the blamed step, or the flagged check.
    const last = forestRowDelay({ index: 5, total: 6, reduced: false })
    const deferred = forestRowDelay({ index: 1, total: 6, deferred: true, reduced: false })

    // Assert
    expect(deferred).toBeGreaterThan(last)
  })

  test('collapses to zero under reduced motion', () => {
    expect(forestRowDelay({ index: 4, total: 6, reduced: true })).toBe(0)
    expect(forestRowDelay({ index: 1, total: 6, deferred: true, reduced: true })).toBe(0)
  })
})

describe('forestWhiskerMotion', () => {
  test('draws outward from the estimate', () => {
    // Act
    const motion = forestWhiskerMotion(0.12, false)

    // Assert
    expect(motion.initial).toEqual({ scaleX: 0 })
    expect(motion.animate).toEqual({ scaleX: 1 })
    expect(motion.transition).toMatchObject({ type: 'spring', delay: 0.12 })
  })

  test('starts at the final state under reduced motion', () => {
    // Act
    const motion = forestWhiskerMotion(0.12, true)

    // Assert — `false` skips the initial state rather than animating to it.
    expect(motion.initial).toBe(false)
    expect(motion.transition).toMatchObject({ duration: 0, delay: 0 })
  })
})

describe('forestDotMotion', () => {
  test('pops in after its own whisker', () => {
    // Act
    const whisker = forestWhiskerMotion(0.12, false)
    const dot = forestDotMotion(0.12, false)

    // Assert
    expect(dot.animate).toEqual({ scale: 1 })
    const whiskerDelay = (whisker.transition as { delay: number }).delay
    const dotDelay = (dot.transition as { delay: number }).delay
    expect(dotDelay - whiskerDelay).toBeCloseTo(FOREST_DOT_LAG_SECONDS, 6)
  })

  test('lands with its row under reduced motion', () => {
    const dot = forestDotMotion(0.12, true)
    expect(dot.initial).toBe(false)
    expect(dot.transition).toMatchObject({ duration: 0, delay: 0 })
  })
})
