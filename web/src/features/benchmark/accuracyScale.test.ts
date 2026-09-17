import { describe, expect, test } from 'vitest'

import { accuracyAxisMax, axisTicks, rateFraction, rateSpanPercent } from './accuracyScale'

/** Best judge 87.2% + the pre-registered 15 points lands at 102.2%. */
const UNATTAINABLE_BAR = 1.0221

describe('axisTicks', () => {
  test('is the fixed quarters while the scale ends at 100%', () => {
    expect(axisTicks(1)).toEqual([0, 0.25, 0.5, 0.75, 1])
  })

  test('adds a tick at the axis maximum once the bar pushes past 100%', () => {
    // Arrange
    const axisMax = accuracyAxisMax(UNATTAINABLE_BAR)

    // Act
    const ticks = axisTicks(axisMax)

    // Assert — the last tick is the track's right edge, so the axis and the
    // bars agree about where the scale ends.
    expect(ticks.at(-1)).toBe(axisMax)
    expect(rateFraction(ticks.at(-1) ?? 0, axisMax)).toBe(1)
  })

  test('keeps 100% inside the track once the axis runs past it', () => {
    const axisMax = accuracyAxisMax(UNATTAINABLE_BAR)
    expect(rateFraction(1, axisMax)).toBeLessThan(1)
  })
})

describe('accuracyAxisMax', () => {
  test('stays at 100% for a bar that can be reached', () => {
    expect(accuracyAxisMax(0.964)).toBe(1)
    expect(accuracyAxisMax(undefined)).toBe(1)
  })

  test('grows just past an unattainable bar so it stays on screen', () => {
    const axisMax = accuracyAxisMax(UNATTAINABLE_BAR)
    expect(axisMax).toBeGreaterThan(UNATTAINABLE_BAR)
    expect(axisMax).toBeLessThan(UNATTAINABLE_BAR + 0.05)
  })
})

describe('rateSpanPercent', () => {
  test('is the distance between two rates on the drawn track', () => {
    expect(rateSpanPercent(0.25, 0.75, 1)).toBe('50.000%')
  })

  test('never goes negative when the bounds arrive the wrong way round', () => {
    expect(rateSpanPercent(0.75, 0.25, 1)).toBe('0.000%')
  })
})
