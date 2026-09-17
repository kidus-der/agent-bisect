import { describe, expect, test } from 'vitest'

import { formatPercent, formatPoints, headlineBars, headlineGap } from './headline'
import type { HeadlineResult } from './api'

const HEADLINE: HeadlineResult = {
  bisect: { value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 },
  best_judge: { value: 0.8721, ci_low: 0.7853, ci_high: 0.9271 },
  best_judge_method: 'judge_step_by_step',
}

describe('formatPercent', () => {
  test('renders a proportion as a one-decimal percentage', () => {
    expect(formatPercent(0.9651)).toBe('96.5%')
    expect(formatPercent(0.8)).toBe('80.0%')
  })

  test('renders a non-finite value as n/a rather than NaN%', () => {
    expect(formatPercent(Number.NaN)).toBe('n/a')
  })
})

describe('formatPoints', () => {
  test('renders a signed gap in percentage points', () => {
    expect(formatPoints(0.093)).toBe('+9.3 pts')
    expect(formatPoints(-0.093)).toBe('−9.3 pts')
  })
})

describe('headlineBars', () => {
  test('puts Bisect first and gives each method its fixed colour role', () => {
    const bars = headlineBars(HEADLINE)
    expect(bars.map((bar) => bar.id)).toEqual(['bisect', 'best_judge'])
    expect(bars[0]).toMatchObject({ role: 'measure', label: 'Bisect', value: 0.9651 })
    expect(bars[1]).toMatchObject({ role: 'judge', label: 'Judge · step by step' })
  })

  test('carries the 95% interval belonging to each bar', () => {
    const [bisect] = headlineBars(HEADLINE)
    expect(bisect).toMatchObject({ low: 0.9024, high: 0.9881 })
  })
})

describe('headlineGap', () => {
  test('reports the gap in percentage points', () => {
    expect(headlineGap(HEADLINE).points).toBeCloseTo(0.093, 6)
  })

  test('reports that the interval for the gap itself is not measured here', () => {
    // /api/overview carries a CI per method but none for their difference, and a
    // difference-of-proportions interval would be the wrong estimator for two
    // methods scored on the same dataset. Better absent than invented.
    expect(headlineGap(HEADLINE).interval).toBeNull()
  })

  test('stays signed when the judge is ahead', () => {
    const flipped: HeadlineResult = { ...HEADLINE, bisect: HEADLINE.best_judge, best_judge: HEADLINE.bisect }
    expect(headlineGap(flipped).points).toBeLessThan(0)
  })
})
