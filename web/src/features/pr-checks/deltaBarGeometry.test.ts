import { describe, expect, test } from 'vitest'

import { ZERO_MIDPOINT_PERCENT, deltaBarGeometry } from './deltaBarGeometry'

/** The worst change in the suite; every bar is drawn against it. */
const SCALE = 0.67

describe('deltaBarGeometry', () => {
  test('a negative change runs left from the midpoint', () => {
    // Act — the worst row fills the whole left half.
    const worst = deltaBarGeometry(-0.67, SCALE)

    // Assert
    expect(worst.left).toBeCloseTo(0, 6)
    expect(worst.left + worst.width).toBeCloseTo(50, 6)
  })

  test('a positive change runs right from the midpoint', () => {
    // Act
    const best = deltaBarGeometry(0.67, SCALE)

    // Assert
    expect(best.left).toBeCloseTo(50, 6)
    expect(best.left + best.width).toBeCloseTo(100, 6)
  })

  test('every bar touches the midpoint, whichever way it points', () => {
    // Arrange / Act / Assert — this is what makes the axis legend true.
    for (const value of [-0.67, -0.44, -0.01, 0.01, 0.2, 0.67]) {
      const bar = deltaBarGeometry(value, SCALE)
      const touchesMidpoint = bar.left === 50 || Math.abs(bar.left + bar.width - 50) < 1e-9
      expect(touchesMidpoint).toBe(true)
    }
  })

  test('length is proportional to size, independent of sign', () => {
    expect(deltaBarGeometry(-0.335, SCALE).width).toBeCloseTo(
      deltaBarGeometry(0.335, SCALE).width,
      6,
    )
    expect(deltaBarGeometry(-0.335, SCALE).width).toBeCloseTo(25, 6)
  })

  test('clamps a change larger than the scale rather than overflowing', () => {
    const over = deltaBarGeometry(-1, 0.5)
    expect(over.left).toBeCloseTo(0, 6)
    expect(over.width).toBeCloseTo(50, 6)
  })

  test('the zero rule sits at the same x as every bar anchor', () => {
    // Arrange — the rule down the column and the tick in the key are both drawn
    // at ZERO_MIDPOINT_PERCENT; the bars must anchor at that exact x or the rule
    // is decoration rather than the axis it claims to be.
    const negative = deltaBarGeometry(-0.44, SCALE)
    const positive = deltaBarGeometry(0.2, SCALE)

    // Assert
    expect(negative.left + negative.width).toBeCloseTo(ZERO_MIDPOINT_PERCENT, 9)
    expect(positive.left).toBeCloseTo(ZERO_MIDPOINT_PERCENT, 9)
  })

  test('draws nothing for a zero change or an unusable scale', () => {
    expect(deltaBarGeometry(0, SCALE)).toEqual({ left: 50, width: 0 })
    expect(deltaBarGeometry(-0.5, 0)).toEqual({ left: 50, width: 0 })
    expect(deltaBarGeometry(Number.NaN, SCALE)).toEqual({ left: 50, width: 0 })
  })
})
