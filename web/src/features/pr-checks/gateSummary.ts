/**
 * What the gate has actually found across every check it has run.
 *
 * Every figure here is derived from the list payload the page already has —
 * nothing is fetched, assumed or invented. The median is used rather than the
 * mean because six checks split three-and-three around zero, where a mean says
 * less than the middle does.
 */
import { type IntervalEstimate, newcombeInterval } from '@/lib/stats'

import type { PrCheckSummary } from './api'

/** The suite is 24 scenarios × 4 runs on each ref (see any check's detail). */
export const RUNS_PER_REF = 96

export interface CheckDelta {
  readonly checkId: string
  /** Null when the gate compared two refs rather than a pull request. */
  readonly prNumber: number | null
  readonly title: string
  readonly isRegression: boolean
  readonly delta: number
  /** Null when the run count cannot support an interval. */
  readonly interval: IntervalEstimate | null
  /** True when that interval excludes zero — the only case worth colouring. */
  readonly decisive: boolean
}

export interface GateSummary {
  readonly deltas: readonly CheckDelta[]
  readonly regressions: number
  readonly clean: number
  /** Median change across every check, in rate units. */
  readonly medianDelta: number
  /** The worst single check, for the axis. */
  readonly worstDelta: number
  readonly bestDelta: number
  /** How many changes the interval actually separates from zero. */
  readonly decisiveCount: number
}

export function checkDelta(check: PrCheckSummary): CheckDelta {
  const delta = check.head_pass_rate - check.base_pass_rate
  const interval = newcombeInterval(
    check.head_pass_rate,
    RUNS_PER_REF,
    check.base_pass_rate,
    RUNS_PER_REF,
  )
  return {
    checkId: check.check_id,
    prNumber: check.pr_number,
    title: check.title,
    isRegression: check.is_regression,
    delta,
    interval,
    decisive: interval !== null && (interval.low > 0 || interval.high < 0),
  }
}

function median(values: readonly number[]): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) return sorted[middle] ?? 0
  return ((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2
}

export function buildGateSummary(checks: readonly PrCheckSummary[]): GateSummary {
  const deltas = checks.map(checkDelta)
  const values = deltas.map((entry) => entry.delta)
  return {
    deltas,
    regressions: deltas.filter((entry) => entry.isRegression).length,
    clean: deltas.filter((entry) => !entry.isRegression).length,
    medianDelta: median(values),
    worstDelta: values.length === 0 ? 0 : Math.min(...values),
    bestDelta: values.length === 0 ? 0 : Math.max(...values),
    decisiveCount: deltas.filter((entry) => entry.decisive).length,
  }
}

/**
 * Symmetric axis bound, so zero sits in the middle and both sides are
 * comparable. It reaches the end of the widest *interval*, not the widest point
 * estimate: an interval drawn past the axis is clipped at the edge, and a
 * clipped whisker reads as an interval that stops there.
 */
export function deltaAxisBound(summary: GateSummary): number {
  const reach = summary.deltas.flatMap((entry) =>
    entry.interval
      ? [Math.abs(entry.delta), Math.abs(entry.interval.low), Math.abs(entry.interval.high)]
      : [Math.abs(entry.delta)],
  )
  const widest = reach.length === 0 ? 0 : Math.max(...reach)
  return widest > 0 ? widest : 1
}
