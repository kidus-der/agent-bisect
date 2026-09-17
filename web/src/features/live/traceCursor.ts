import type { SeriesPoint } from './callsSeries'

/**
 * The sample a shared time cursor lands on.
 *
 * The cursor is carried across the traces as a *time*, not a pixel: two models
 * can be sampled on different clocks, and snapping each trace to its own nearest
 * sample is the only reading that does not invent a value for the other one.
 * Ties go to the earlier sample so both traces agree on the same instant.
 */
export function nearestPoint(points: readonly SeriesPoint[], time: number): SeriesPoint | null {
  let best: SeriesPoint | null = null
  let bestDistance = Number.POSITIVE_INFINITY
  for (const point of points) {
    const distance = Math.abs(point.time - time)
    if (distance < bestDistance) {
      best = point
      bestDistance = distance
    }
  }
  return best
}
