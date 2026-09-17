import { describe, expect, test } from 'vitest'

import { accuracyAxisMax, axisTicks, rateFraction, rateSpanPercent } from './accuracyScale'

/** Best judge 87.2% + the pre-registered 15 points lands at 102.2%. */
const UNATTAINABLE_BAR = 1.0221

describe('axisTicks', () => {
  test('is the fixed quarters while the scale ends at 100%', () => {
    expect(axisTicks(1)).toEqual([0, 0.25, 0.5, 0.75, 1])
  })

  test('does not label an axis maximum that would collide with 100%', () => {
    // Arrange — the real bar puts the axis end about four points past 100%,
    // which is closer than two mono labels can sit without overprinting.
    const axisMax = accuracyAxisMax(UNATTAINABLE_BAR)

    // Act
    const ticks = axisTicks(axisMax)

    // Assert — 100% is the number that means something, so it is the one kept.
    expect(ticks).toEqual([0, 0.25, 0.5, 0.75, 1])
  })

  test('labels the axis maximum once it is far enough past 100% to be legible', () => {
    // Act — an axis half as long again as the rates it carries.
    const ticks = axisTicks(1.5)

    // Assert
    expect(ticks.at(-1)).toBe(1.5)
    expect(rateFraction(ticks.at(-1) ?? 0, 1.5)).toBe(1)
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
