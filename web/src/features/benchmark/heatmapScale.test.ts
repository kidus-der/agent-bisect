import { describe, expect, test } from 'vitest'

import { contrastRatio } from '@/design/color'
import { THEME_NAMES, themes } from '@/design/tokens'

import { HEATMAP_STEPS, heatmapRamp, rampDomain, rampStep } from './heatmapScale'

describe('heatmapRamp', () => {
  test.each(THEME_NAMES)('every %s step clears AA against its own ink', (theme) => {
    // Act
    const ramp = heatmapRamp(theme)

    // Assert — every cell prints its value on this fill, with no plate behind it.
    expect(ramp).toHaveLength(HEATMAP_STEPS)
    for (const step of ramp) {
      expect(contrastRatio(step.fill, step.text)).toBeGreaterThanOrEqual(4.5)
    }
  })

  test.each(THEME_NAMES)('%s steps get progressively stronger', (theme) => {
    // Arrange / Act
    const ramp = heatmapRamp(theme)

    // Assert — a strictly changing ramp, so two neighbouring values never look equal.
    const unique = new Set(ramp.map((step) => step.fill))
    expect(unique.size).toBe(HEATMAP_STEPS)
  })

  test.each(THEME_NAMES)('%s spans a range wide enough to read as a ramp', (theme) => {
    // Arrange / Act — holding one ink capped the dark ramp at five near-identical
    // teals; the span is what makes a heatmap a heatmap.
    const ramp = heatmapRamp(theme)
    const surface = themes[theme].neutral.surface
    const weakest = contrastRatio(ramp[0]?.fill ?? surface, surface)
    const strongest = contrastRatio(ramp[HEATMAP_STEPS - 1]?.fill ?? surface, surface)

    // Assert
    expect(strongest / weakest).toBeGreaterThan(3)
  })

  test.each(THEME_NAMES)('%s runs weakest first in both themes', (theme) => {
    // Arrange — more hue means a brighter fill on a dark surface and a darker
    // one on a light surface, so the order is by hue strength, not luminance.
    const ramp = heatmapRamp(theme)
    const surface = themes[theme].neutral.surface

    // Act
    const strengths = ramp.map((step) => contrastRatio(step.fill, surface))

    // Assert
    expect([...strengths].sort((a, b) => a - b)).toEqual(strengths)
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
