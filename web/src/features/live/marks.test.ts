import { describe, expect, test } from 'vitest'

import { contrastRatio } from '@/design/color'
import { THEME_NAMES, themes } from '@/design/tokens'

import { REMAINING_MARK_ROLE } from './marks'

/** WCAG 1.4.11: a non-text mark that carries meaning needs 3:1. */
const AA_NON_TEXT = 3

describe('the remaining-portion mark', () => {
  test.each(THEME_NAMES)('clears 3:1 on %s surface and ground', (themeName) => {
    // Arrange
    const theme = themes[themeName]
    const mark = theme.role[REMAINING_MARK_ROLE]

    // Assert — the gauge's unfilled ticks and the ring's track are what show
    // how much budget is left; they are data, not chrome.
    expect(contrastRatio(mark, theme.neutral.surface)).toBeGreaterThanOrEqual(AA_NON_TEXT)
    expect(contrastRatio(mark, theme.neutral.ground)).toBeGreaterThanOrEqual(AA_NON_TEXT)
  })

  test.each(THEME_NAMES)('the hairline tokens it replaced do not, in %s', (themeName) => {
    // Arrange — this is why `line` / `line-strong` cannot be used here.
    const theme = themes[themeName]

    // Assert
    const line = contrastRatio(theme.neutral.line, theme.neutral.surface)
    const lineStrong = contrastRatio(theme.neutral.lineStrong, theme.neutral.surface)
    expect(Math.min(line, lineStrong)).toBeLessThan(AA_NON_TEXT)
  })
})
