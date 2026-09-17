/** Sequential colour scale for the blame stripe and the minimap. */

const SCALE_BUCKETS = 5

/**
 * Effect -> one of the five sequential steps. A negative effect (fixing the step
 * made things worse) lands in the lightest bucket; the readout still carries the
 * sign, so the colour never has to.
 */
export function heatBucket(effect: number): string {
  const clamped = Math.min(1, Math.max(0, effect))
  const bucket = Math.min(SCALE_BUCKETS, Math.floor(clamped * SCALE_BUCKETS) + 1)
  return `var(--chart-scale-0${bucket})`
}
