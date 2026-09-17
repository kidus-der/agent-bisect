import { describe, expect, test } from 'vitest'

import { contrastRatio } from '@/design/color'
import { THEME_NAMES, themes } from '@/design/tokens'

import { HEATMAP_STEPS, heatmapRamp, rampDomain, rampStep } from './heatmapScale'

describe('heatmapRamp', () => {
  test.each(THEME_NAMES)('every %s step clears AA against the cell text', (theme) => {
    // Arrange
    const ink = themes[theme].neutral.text

    // Act
    const ramp = heatmapRamp(theme)

    // Assert — every cell prints its value on this fill, with no plate behind it.
    expect(ramp).toHaveLength(HEATMAP_STEPS)
    for (const fill of ramp) {
      expect(contrastRatio(fill, ink)).toBeGreaterThanOrEqual(4.5)
    }
  })

  test.each(THEME_NAMES)('%s steps get progressively stronger', (theme) => {
    // Arrange / Act
    const ramp = heatmapRamp(theme)

    // Assert — a strictly changing ramp, so two neighbouring values never look equal.
    const unique = new Set(ramp)
    expect(unique.size).toBe(HEATMAP_STEPS)
  })
})

describe('rampDomain', () => {
  test('spans the observed values', () => {
    expect(rampDomain([0.5, 0.9, 0.7])).toEqual({ min: 0.5, max: 0.9 })
  })

  test('falls back to the full rate range when there is nothing to measure', () => {
    expect(rampDomain([])).toEqual({ min: 0, max: 1 })
  })
})

describe('rampStep', () => {
  test('puts the lowest value on the lightest step and the highest on the darkest', () => {
    // Arrange
    const domain = { min: 0.5, max: 1 }

    // Assert
    expect(rampStep(0.5, domain)).toBe(0)
    expect(rampStep(1, domain)).toBe(HEATMAP_STEPS - 1)
  })

  test('clamps a value outside the domain', () => {
    const domain = { min: 0.5, max: 1 }
    expect(rampStep(0.1, domain)).toBe(0)
    expect(rampStep(1.4, domain)).toBe(HEATMAP_STEPS - 1)
  })

  test('puts a flat domain on the darkest step rather than dividing by zero', () => {
    expect(rampStep(0.8, { min: 0.8, max: 0.8 })).toBe(HEATMAP_STEPS - 1)
  })
})
