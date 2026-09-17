/**
 * The API only sends the cost-histogram bins that contain something, so the
 * series has holes in it. A histogram with a hole silently rescales the x-axis
 * and makes two non-adjacent bins look adjacent, so the empty bins are put back
 * with a count of zero — which is a measurement, not a guess.
 */
import type { CostBucket } from './api'

export function fillBinGaps(bins: readonly CostBucket[]): readonly CostBucket[] {
  if (bins.length === 0) return []
  const sorted = [...bins].sort((a, b) => a.calls_low - b.calls_low)
  const width = sorted.reduce(
    (smallest, bin) => Math.min(smallest, bin.calls_high - bin.calls_low),
    Number.POSITIVE_INFINITY,
  )
  if (!Number.isFinite(width) || width <= 0) return sorted

  const first = sorted[0]
  const last = sorted[sorted.length - 1]
  if (!first || !last) return sorted

  const byLow = new Map(sorted.map((bin) => [bin.calls_low, bin]))
  const filled: CostBucket[] = []
  for (let low = first.calls_low; low < last.calls_high; low += width) {
    filled.push(byLow.get(low) ?? { calls_low: low, calls_high: low + width, count: 0 })
  }
  return filled
}

export function maxBinCount(bins: readonly CostBucket[]): number {
  return bins.reduce((largest, bin) => Math.max(largest, bin.count), 0)
}

export function totalBinCount(bins: readonly CostBucket[]): number {
  return bins.reduce((sum, bin) => sum + bin.count, 0)
}
