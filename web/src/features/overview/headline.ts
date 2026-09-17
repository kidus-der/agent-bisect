/**
 * The headline claim as plain data: two bars with their intervals, and the gap
 * between them. Kept pure so the numbers are testable without rendering.
 */
import { type HeadlineResult, methodLabel } from './api'

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
   * The server's paired bootstrap interval for the difference — the right
   * estimator here, because both methods are scored on the same failures.
   * Never derived in the UI from the two per-method intervals.
   */
  readonly low: number
  readonly high: number
  /** True when the interval clears zero, which is the claim being made. */
  readonly beatsZero: boolean
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
  const { value, ci_low: low, ci_high: high } = headline.gap
  return { points: value, low, high, beatsZero: low > 0 }
}
