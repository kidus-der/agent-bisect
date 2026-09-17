import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, test } from 'vitest'

import { contrastRatio } from '@/design/color'
import { themes } from '@/design/tokens'

import { heatmapRamp } from './heatmapScale'

/**
 * The heat ramp is mixed over `surface` (see `heatmapScale`), and its lightest
 * step clears 3:1 on that fill by 0.02 in light theme. Drawn on any other panel
 * fill the same step measures below 3:1 and the matrix stops being a legible
 * data mark — p6d found 2.58:1 on the `recessed` fill that `kpi` now uses.
 *
 * `import.meta.url` is not a file URL under jsdom, so the source is located
 * from the working directory, as in `blameColourGuard`.
 */
const HEATMAP_SOURCE = join(process.cwd(), 'src', 'features', 'benchmark', 'AccuracyHeatmap.tsx')
/** The Panel variants filled with `surface`. */
const SURFACE_VARIANTS = ['card', 'chart']
const NON_TEXT_AA = 3

describe('the accuracy matrix sits on a surface panel', () => {
  test('its Panel asks for a surface-filled variant', () => {
    // Arrange / Act
    const source = readFileSync(HEATMAP_SOURCE, 'utf8')
    const variant = /<Panel\s+variant="([a-z]+)"/.exec(source)?.[1]

    // Assert
    expect(variant).toBeDefined()
    expect(SURFACE_VARIANTS).toContain(variant)
  })

  test('a step that clears the mark floor on surface loses it on recessed', () => {
    // Arrange — light step 3 measures 3.17:1 on `surface` and 2.58:1 on
    // `recessed`. The panel fill is therefore the difference between a ramp that
    // meets 1.4.11 and one that does not, which is the whole reason the variant
    // above is pinned rather than left to taste.
    for (const theme of ['light', 'dark'] as const) {
      const { neutral } = themes[theme]

      // Act
      const brokenByRecessing = heatmapRamp(theme).filter(
        (step) =>
          contrastRatio(step.fill, neutral.surface) >= NON_TEXT_AA &&
          contrastRatio(step.fill, neutral.recessed) < NON_TEXT_AA,
      )

      // Assert
      expect(brokenByRecessing.length).toBeGreaterThan(0)
    }
  })
})
