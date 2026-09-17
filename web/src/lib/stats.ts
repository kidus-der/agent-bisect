/**
 * The two interval formulas the product itself runs on (brief §2): Wilson for a
 * single proportion, Newcombe for the difference of two.
 *
 * The API returns a bootstrap CI wherever it has computed one. Where it returns
 * only a rate and an `n` (`HeatmapCell`, `PositionAccuracy`, `ScenarioRow`,
 * `PrCheckSummary`), these recompute the interval on the client rather than let
 * an estimate be drawn without one. Every one of them returns `null` instead of
 * inventing a number when the inputs cannot support an interval.
 */

/** Two-sided 95% normal quantile. Both formulas below are fixed at 95%. */
const Z_95 = 1.959963984540054
const HALF = 2
const QUARTER = 4

export interface Interval {
  readonly low: number
  readonly high: number
}

export interface IntervalEstimate extends Interval {
  readonly value: number
}

function isUsableSample(rate: number, n: number): boolean {
  return Number.isFinite(rate) && Number.isFinite(n) && n > 0 && rate >= 0 && rate <= 1
}

function clampToUnit(value: number): number {
  return Math.min(1, Math.max(0, value))
}

/**
 * Wilson score interval for a proportion observed as `rate` over `n` trials.
 * Preferred over the normal approximation because it stays inside [0, 1] and
 * still has a usable width at rates of 0 and 1 — both of which occur in the
 * benchmark heatmap.
 */
export function wilsonInterval(rate: number, n: number): Interval | null {
  if (!isUsableSample(rate, n)) return null
  const zSquaredOverN = (Z_95 * Z_95) / n
  const denominator = 1 + zSquaredOverN
  const centre = (rate + zSquaredOverN / HALF) / denominator
  const spread =
    (Z_95 / denominator) * Math.sqrt((rate * (1 - rate)) / n + (Z_95 * Z_95) / (QUARTER * n * n))
  return { low: clampToUnit(centre - spread), high: clampToUnit(centre + spread) }
}

/**
 * Newcombe's hybrid-score interval for `rate - baselineRate`, built from the two
 * Wilson intervals. This is the interval the estimator uses for `effect(k)`.
 */
export function newcombeInterval(
  rate: number,
  n: number,
  baselineRate: number,
  baselineN: number,
): IntervalEstimate | null {
  const treated = wilsonInterval(rate, n)
  const control = wilsonInterval(baselineRate, baselineN)
  if (!treated || !control) return null
  const difference = rate - baselineRate
  const lowerSpread = Math.hypot(rate - treated.low, control.high - baselineRate)
  const upperSpread = Math.hypot(treated.high - rate, baselineRate - control.low)
  return {
    value: difference,
    low: Math.max(-1, difference - lowerSpread),
    high: Math.min(1, difference + upperSpread),
  }
}

const DEFAULT_PERCENT_DECIMALS = 1
const PERCENT = 100

/** `0.9651` -> `96.5%`. Tabular numerals come from the `num` utility at the call site. */
export function formatPercent(rate: number, decimals = DEFAULT_PERCENT_DECIMALS): string {
  if (!Number.isFinite(rate)) return 'n/a'
  return `${(rate * PERCENT).toFixed(decimals)}%`
}

/**
 * Signed percentage-point difference: `+10.5 pts`, `−4.0 pts`, `0.0 pts`.
 *
 * The sign comes from the rounded magnitude, not the raw value: a difference
 * of -0.0001 displays as `0.0 pts`, never `−0.0 pts`, which would claim a
 * direction the rounding has already erased.
 */
export function formatPoints(difference: number, decimals = DEFAULT_PERCENT_DECIMALS): string {
  if (!Number.isFinite(difference)) return 'n/a'
  const points = difference * PERCENT
  const magnitude = Math.abs(points).toFixed(decimals)
  const sign = Number(magnitude) === 0 ? '' : points > 0 ? '+' : '−'
  return `${sign}${magnitude} pts`
}

const P_VALUE_DECIMALS = 3
const SMALLEST_REPORTED_P = 0.001

/** A p value is reported, never rounded to a flat `0.000`. */
export function formatPValue(pValue: number): string {
  if (!Number.isFinite(pValue)) return 'n/a'
  if (pValue < SMALLEST_REPORTED_P) return `< ${SMALLEST_REPORTED_P.toFixed(P_VALUE_DECIMALS)}`
  return pValue.toFixed(P_VALUE_DECIMALS)
}
