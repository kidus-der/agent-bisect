import { describe, expect, test } from 'vitest'

import { formatPercent, formatPoints, headlineBars, headlineGap } from './headline'
import type { HeadlineResult } from './api'

const HEADLINE: HeadlineResult = {
  bisect: { value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 },
  best_judge: { value: 0.8721, ci_low: 0.7853, ci_high: 0.9271 },
  best_judge_method: 'judge_step_by_step',
  gap: { value: 0.1512, ci_low: 0.0581, ci_high: 0.2442 },
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
  test('reports the server\u2019s paired estimate, not a difference of the two bars', () => {
    const gap = headlineGap(HEADLINE)
    expect(gap.points).toBeCloseTo(0.1512, 6)
    expect(gap).toMatchObject({ low: 0.0581, high: 0.2442 })
    // Subtracting the two point estimates would give 0.093; the paired bootstrap does not.
    expect(gap.points).not.toBeCloseTo(HEADLINE.bisect.value - HEADLINE.best_judge.value, 3)
  })

  test('says whether the interval clears zero', () => {
    expect(headlineGap(HEADLINE).beatsZero).toBe(true)
    const straddling: HeadlineResult = {
      ...HEADLINE,
      gap: { value: 0.02, ci_low: -0.04, ci_high: 0.08 },
    }
    expect(headlineGap(straddling).beatsZero).toBe(false)
  })
})
