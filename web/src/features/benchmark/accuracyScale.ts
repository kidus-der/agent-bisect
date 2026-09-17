/**
 * The shared 0 -> axis-max accuracy scale used by the method comparison.
 *
 * The axis normally ends at 100%. It only ever grows past that to keep the
 * pre-registered bar on screen when the bar itself lands above 100% — the region
 * beyond 100% is then drawn hatched, as unreachable, rather than hidden.
 */

export const MAX_RATE = 1
export const AXIS_TICKS = [0, 0.25, 0.5, 0.75, 1] as const

/** Kept clear to the right of the furthest mark so its label is not clipped. */
const AXIS_HEADROOM = 0.02
const PERCENT = 100

export function accuracyAxisMax(threshold?: number): number {
  if (threshold === undefined || !Number.isFinite(threshold)) return MAX_RATE
  return Math.max(MAX_RATE, threshold + AXIS_HEADROOM)
}

/** Fraction of the axis a rate occupies, clamped to the drawn range. */
export function rateFraction(rate: number, axisMax: number): number {
  if (!Number.isFinite(rate) || axisMax <= 0) return 0
  return Math.min(1, Math.max(0, rate / axisMax))
}

/** The same fraction as a CSS percentage, for `left` / `width`. */
export function ratePercent(rate: number, axisMax: number): string {
  return `${(rateFraction(rate, axisMax) * PERCENT).toFixed(3)}%`
}

/** Width of the span between two rates, as a CSS percentage. */
export function rateSpanPercent(low: number, high: number, axisMax: number): string {
  const span = rateFraction(high, axisMax) - rateFraction(low, axisMax)
  return `${(Math.max(0, span) * PERCENT).toFixed(3)}%`
}
