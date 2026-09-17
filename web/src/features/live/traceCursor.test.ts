import { describe, expect, test } from 'vitest'

import type { SeriesPoint } from './callsSeries'
import { nearestPoint, stepCursor } from './traceCursor'

const POINTS: readonly SeriesPoint[] = [
  { time: 100, value: 1 },
  { time: 130, value: 4 },
  { time: 160, value: 2 },
]

describe('nearestPoint', () => {
  test('snaps to the sample the cursor is closest to', () => {
    // Arrange / Act
    const point = nearestPoint(POINTS, 136)

    // Assert — 136 is 6s past the middle sample and 24s short of the last.
    expect(point).toEqual({ time: 130, value: 4 })
  })

  test('clamps to the ends rather than reading off the series', () => {
    expect(nearestPoint(POINTS, 0)?.time).toBe(100)
    expect(nearestPoint(POINTS, 9999)?.time).toBe(160)
  })

  test('takes the earlier sample when the cursor sits exactly between two', () => {
    // A stable choice matters: the two traces must not disagree on a tie.
    expect(nearestPoint(POINTS, 115)?.time).toBe(100)
  })

  test('has nothing to snap to in an empty series', () => {
    expect(nearestPoint([], 120)).toBeNull()
  })
})

describe('stepCursor', () => {
  test('moves one sample at a time in either direction', () => {
    expect(stepCursor(POINTS, 130, 1)).toBe(160)
    expect(stepCursor(POINTS, 130, -1)).toBe(100)
  })

  test('stops at the ends rather than wrapping round', () => {
    expect(stepCursor(POINTS, 160, 1)).toBe(160)
    expect(stepCursor(POINTS, 100, -1)).toBe(100)
  })

  test('snaps a cursor resting between samples onto the series first', () => {
    // Arrange / Act — 136 is nearest 130, so one step right is 160.
    expect(stepCursor(POINTS, 136, 1)).toBe(160)
  })

  test('has nowhere to step in an empty series', () => {
    expect(stepCursor([], 120, 1)).toBeNull()
  })
})
