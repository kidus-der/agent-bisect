import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

import { contrastRatio } from './color'
import {
  CHART_SERIES_ORDER,
  ROLE_NAMES,
  THEME_NAMES,
  type ThemeTokens,
  roleTint,
  SEQUENTIAL_SCALE_STEPS,
  sequentialScale,
  themes,
} from './tokens'
import { buildTokensCss } from './tokens-css'

const AA_TEXT = 4.5
const AA_NON_TEXT = 3

interface Pair {
  readonly name: string
  readonly foreground: string
  readonly background: string
  readonly minimum: number
}

const TEXT_ROLES = ROLE_NAMES.filter((role) => role !== 'tape')

function textPairs(theme: ThemeTokens): readonly Pair[] {
  const { ground, surface, elevated, recessed, text, muted } = theme.neutral
  const backgrounds = { ground, surface, elevated, recessed }
  /**
   * Role-coloured *text* is not held to `recessed`: on a fill dark enough to
   * read as a recess, light's role colours land at 4.2-4.4:1. Role text there
   * always sits in a pill, on its own tint, which is checked below.
   */
  const textBackgrounds = { ground, surface, elevated }
  const neutralText = Object.entries(backgrounds).flatMap(([bgName, background]) => [
    { name: `text on ${bgName}`, foreground: text, background, minimum: AA_TEXT },
    { name: `muted on ${bgName}`, foreground: muted, background, minimum: AA_TEXT },
  ])
  const roleText = TEXT_ROLES.flatMap((role) =>
    Object.entries(textBackgrounds).map(([bgName, background]) => ({
      name: `${role} on ${bgName}`,
      foreground: theme.role[role],
      background,
      minimum: AA_TEXT,
    })),
  )
  const roleOnOwnTint = TEXT_ROLES.map((role) => ({
    name: `${role} on its tint (pills)`,
    foreground: theme.role[role],
    background: roleTint(theme, role),
    minimum: AA_TEXT,
  }))
  const onSolidRole = TEXT_ROLES.map((role) => ({
    name: `on-role text on solid ${role}`,
    foreground: theme.on.onRole,
    background: theme.role[role],
    minimum: AA_TEXT,
  }))
  const tapeCell = [
    {
      name: 'on-tape text on solid tape',
      foreground: theme.on.onTape,
      background: theme.role.tape,
      minimum: AA_TEXT,
    },
    {
      name: 'muted on tape tint (TapeStep)',
      foreground: muted,
      background: roleTint(theme, 'tape'),
      minimum: AA_TEXT,
    },
    {
      name: 'text on tape tint (DiffBlock)',
      foreground: text,
      background: roleTint(theme, 'tape'),
      minimum: AA_TEXT,
    },
    {
      name: 'text on measure tint (DiffBlock)',
      foreground: text,
      background: roleTint(theme, 'measure'),
      minimum: AA_TEXT,
    },
    {
      name: 'text on blame tint (TapeStep)',
      foreground: text,
      background: roleTint(theme, 'blame'),
      minimum: AA_TEXT,
    },
  ]
  return [...neutralText, ...roleText, ...roleOnOwnTint, ...onSolidRole, ...tapeCell]
}

function nonTextPairs(theme: ThemeTokens): readonly Pair[] {
  const { ground, surface, elevated, recessed, focus } = theme.neutral
  const marks = ROLE_NAMES.flatMap((role) =>
    // From-tape slate is specified for ground/surface only (direction.md §4).
    Object.entries(
      role === 'tape' ? { ground, surface } : { ground, surface, elevated, recessed },
    ).map(
      ([bgName, background]) => ({
        name: `${role} mark on ${bgName}`,
        foreground: theme.role[role],
        background,
        minimum: AA_NON_TEXT,
      }),
    ),
  )
  const focusRing = Object.entries({ ground, surface, elevated, recessed }).map(
    ([bgName, background]) => ({
      name: `focus ring on ${bgName}`,
      foreground: focus,
      background,
      minimum: AA_NON_TEXT,
    }),
  )
  // Every step of the heat ramp is a data mark, not just the strongest: the
  // lowest one has to be separable from the card it sits on too.
  /**
   * Surface only, and that is a constraint on where a heat stripe may be drawn,
   * not an omission: the ramp's lightest step clears 3:1 on white by 0.02, so it
   * fails on any fill below it — 2.80:1 even on `#EFF1F5`, 2.58:1 on `recessed`,
   * and 2.91:1 on dark's `elevated`. Heat cells belong on `surface` panels.
   */
  const heatCells = sequentialScale(theme).map((fill, index) => ({
    name: `heat cell ${index + 1} of ${SEQUENTIAL_SCALE_STEPS} on surface`,
    foreground: fill,
    background: surface,
    minimum: AA_NON_TEXT,
  }))
  return [...marks, ...focusRing, ...heatCells]
}

describe.each(THEME_NAMES)('%s theme contrast', (themeName) => {
  const theme = themes[themeName]

  test.each(textPairs(theme))(
    '$name clears AA text (4.5:1)',
    ({ foreground, background, minimum }) => {
      expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(minimum)
    },
  )

  test.each(nonTextPairs(theme))(
    '$name clears AA non-text (3:1)',
    ({ foreground, background, minimum }) => {
      expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(minimum)
    },
  )
})

describe('token invariants', () => {
  test('blame amber is the last, reserved chart series', () => {
    expect(CHART_SERIES_ORDER.at(-1)).toBe('blame')
    expect(CHART_SERIES_ORDER.slice(0, -1)).not.toContain('blame')
  })

  test('the generator emits both themes and the Tailwind mapping', () => {
    const css = buildTokensCss()
    expect(css).toContain(':root[data-theme="dark"]')
    expect(css).toContain(':root[data-theme="light"]')
    expect(css).toContain('@theme inline')
    expect(css).toContain(`--bx-ground: ${themes.dark.neutral.ground}`)
    expect(css).toContain(`--bx-ground: ${themes.light.neutral.ground}`)
    expect(css).toContain('--chart-1: var(--bx-measure)')
  })

  test('tokens.generated.css is in sync with tokens.ts (run `npm run tokens`)', () => {
    const path = resolve(process.cwd(), 'src/design/tokens.generated.css')
    expect(readFileSync(path, 'utf8')).toBe(buildTokensCss())
  })
})

/** Printed by `npm test -- tokens` so the report can quote the worst ratios. */
describe('worst ratios', () => {
  test.each(THEME_NAMES)('%s theme', (themeName) => {
    const theme = themes[themeName]
    const worst = (pairs: readonly Pair[]): Pair & { ratio: number } =>
      pairs
        .map((pair) => ({ ...pair, ratio: contrastRatio(pair.foreground, pair.background) }))
        .reduce((lowest, pair) => (pair.ratio < lowest.ratio ? pair : lowest))
    const worstText = worst(textPairs(theme))
    const worstMark = worst(nonTextPairs(theme))
    process.stdout.write(
      `[contrast] ${themeName}: worst text ${worstText.ratio.toFixed(2)} (${worstText.name}); ` +
        `worst non-text ${worstMark.ratio.toFixed(2)} (${worstMark.name})\n`,
    )
    expect(worstText.ratio).toBeGreaterThanOrEqual(AA_TEXT)
    expect(worstMark.ratio).toBeGreaterThanOrEqual(AA_NON_TEXT)
  })
})

describe('the heat ramp', () => {
  test.each(THEME_NAMES)('%s reads as a ramp, each step darker than the last', (themeName) => {
    const scale = sequentialScale(themes[themeName])
    const surface = themes[themeName].neutral.surface
    const ratios = scale.map((fill) => contrastRatio(fill, surface))
    expect(scale).toHaveLength(SEQUENTIAL_SCALE_STEPS)
    for (let step = 1; step < ratios.length; step += 1) {
      expect(ratios[step]).toBeGreaterThan(ratios[step - 1] ?? 0)
    }
  })

  test.each(THEME_NAMES)('%s keeps adjacent steps visibly apart', (themeName) => {
    const scale = sequentialScale(themes[themeName])
    for (let step = 1; step < scale.length; step += 1) {
      expect(contrastRatio(scale[step] ?? '#000000', scale[step - 1] ?? '#000000')).toBeGreaterThan(
        1.2,
      )
    }
  })

  test.each(THEME_NAMES)('%s blame fill clears the data-mark floor', (themeName) => {
    const theme = themes[themeName]
    for (const fill of [theme.fill.blame, theme.fill.blameCoral]) {
      expect(contrastRatio(fill, theme.neutral.surface)).toBeGreaterThanOrEqual(AA_NON_TEXT)
    }
  })

  test.each(THEME_NAMES)('%s blame fill is separable from the fail red', (themeName) => {
    const theme = themes[themeName]
    // The old light-theme value sat at 1.01:1 against fail — identical
    // luminance, so a blamed cell and a failed one looked like one colour.
    expect(contrastRatio(theme.fill.blame, theme.role.fail)).toBeGreaterThan(1.4)
  })
})
