import type { SeriesPoint } from './callsSeries'

/**
 * The sample a shared time cursor lands on.
 *
 * The cursor is carried across the traces as a *time*, not a pixel: two models
 * can be sampled on different clocks, and snapping each trace to its own nearest
 * sample is the only reading that does not invent a value for the other one.
 * Ties go to the earlier sample so both traces agree on the same instant.
 */
/**
 * The time one sample either side of where the cursor is resting.
 *
 * Keyboard users get the same reading as a pointer does, so the cursor has to
 * land on samples rather than on arbitrary times: a cursor between two samples
 * snaps onto the nearer one before it steps, and it stops at the ends rather
 * than wrapping, which would silently jump the reader across the window.
 */
export function stepCursor(
  points: readonly SeriesPoint[],
  time: number,
  direction: 1 | -1,
): number | null {
  const anchor = nearestPoint(points, time)
  if (!anchor) return null
  const index = points.findIndex((point) => point.time === anchor.time)
  const next = points[Math.min(points.length - 1, Math.max(0, index + direction))]
  return next ? next.time : anchor.time
}

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
