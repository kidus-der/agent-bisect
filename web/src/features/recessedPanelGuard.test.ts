import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, test } from 'vitest'

import { contrastRatio } from '@/design/color'
import { themes } from '@/design/tokens'

/**
 * Which of my panels may recede.
 *
 * `kpi` fills with `recessed`, which sits a step away from `surface` — and two
 * of the marks these pages draw are chosen to clear the 3:1 non-text floor
 * against `surface` with almost nothing to spare. Slate (`tape`) measures
 * 3.08:1 on dark `surface` and 2.84:1 on `recessed`; the accuracy ramp's third
 * step measures 3.17:1 and 2.58:1 in light. Either mark on a recessed panel is
 * below the floor, so a panel that draws one has to stay on `surface`.
 *
 * Cyan (`measure`) clears both comfortably, which is why the position plot and
 * the cost histogram are free to recede.
 *
 * `import.meta.url` is not a file URL under jsdom, so sources are located from
 * the working directory, as in `blameColourGuard`.
 */
const FEATURES = ['benchmark', 'live', 'pr-checks'] as const
const FEATURES_DIR = join(process.cwd(), 'src', 'features')
/** A mark that only just clears the floor on `surface`. */
const FRAGILE_MARK = /bg-tape\b|roleColour\('tape'\)|--bx-tape|heatmapRamp\(/
const RECESSED_VARIANT = /variant="kpi"/
const NON_TEXT_AA = 3

function sourcesIn(feature: string): readonly string[] {
  const dir = join(FEATURES_DIR, feature)
  return readdirSync(dir)
    .filter((name) => name.endsWith('.tsx') && !name.includes('.test.'))
    .map((name) => join(dir, name))
}

describe('panels that draw a fragile mark stay on surface', () => {
  test('no component both draws one and asks to recede', () => {
    // Arrange / Act
    const offenders = FEATURES.flatMap(sourcesIn).filter((file) => {
      const source = readFileSync(file, 'utf8')
      return FRAGILE_MARK.test(source) && RECESSED_VARIANT.test(source)
    })

    // Assert — the file names are the message; a bare count says nothing.
    expect(offenders.map((file) => file.slice(FEATURES_DIR.length + 1))).toEqual([])
  })

  test('slate is the mark that makes this rule necessary', () => {
    // Arrange / Act / Assert — if slate ever clears the floor on `recessed`,
    // this rule can be dropped rather than quietly kept out of habit.
    const { neutral, role } = themes.dark
    expect(contrastRatio(role.tape, neutral.surface)).toBeGreaterThanOrEqual(NON_TEXT_AA)
    expect(contrastRatio(role.tape, neutral.recessed)).toBeLessThan(NON_TEXT_AA)
  })
})
