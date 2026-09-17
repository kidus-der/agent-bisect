/**
 * The headline claim as plain data: two bars with their intervals, and the gap
 * between them. Kept pure so the numbers are testable without rendering.
 */
import { formatNumber } from '@/lib/format'

import { type HeadlineResult, methodLabel } from './api'

const PERCENT_DECIMALS = 1
const POINTS_PER_UNIT = 100

/** Colour roles are fixed: cyan is measurement/replay, violet is the judge. */
export type HeadlineRole = 'measure' | 'judge'

export interface HeadlineBar {
  readonly id: 'bisect' | 'best_judge'
  readonly label: string
  readonly role: HeadlineRole
  /** Step accuracy as a proportion in [0, 1]. */
  readonly value: number
  readonly low: number
  readonly high: number
}

export interface HeadlineGap {
  /** Bisect minus the best judge, as a proportion. */
  readonly points: number
  /**
   * `/api/overview` reports a CI per method but none for their difference, and
   * the two methods are scored on the same dataset, so an independent
   * difference-of-proportions interval would be the wrong estimator. The UI
   * says the interval is unavailable rather than inventing one.
   */
  readonly interval: null
}

export function formatPercent(value: number): string {
  return formatNumber(value * POINTS_PER_UNIT, { decimals: PERCENT_DECIMALS, suffix: '%' })
}

export function formatPoints(value: number): string {
  return formatNumber(value * POINTS_PER_UNIT, {
    decimals: PERCENT_DECIMALS,
    signed: true,
    suffix: ' pts',
  })
}

/** Bisect first: it is the claim. The judge is the reference it is measured against. */
export function headlineBars(headline: HeadlineResult): readonly [HeadlineBar, HeadlineBar] {
  return [
    {
      id: 'bisect',
      label: 'Bisect',
      role: 'measure',
      value: headline.bisect.value,
      low: headline.bisect.ci_low,
      high: headline.bisect.ci_high,
    },
    {
      id: 'best_judge',
      label: methodLabel(headline.best_judge_method),
      role: 'judge',
      value: headline.best_judge.value,
      low: headline.best_judge.ci_low,
      high: headline.best_judge.ci_high,
    },
  ]
}

export function headlineGap(headline: HeadlineResult): HeadlineGap {
  return { points: headline.bisect.value - headline.best_judge.value, interval: null }
}
