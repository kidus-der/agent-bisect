/**
 * Shapes `/api/benchmark`'s flat `by_position` rows into one series per method,
 * each point carrying the Wilson interval the API does not send for these rows.
 */
import { type Interval, wilsonInterval } from '@/lib/stats'

import type { MethodName, PositionAccuracy, PositionBucket } from './api'
import { METHOD_ORDER, POSITION_ORDER } from './methods'

export interface PositionPoint {
  readonly position: PositionBucket
  readonly accuracy: number
  readonly n: number
  /** Null when n cannot support an interval; the point is then drawn without a band. */
  readonly interval: Interval | null
}

export interface PositionSeries {
  readonly method: MethodName
  readonly points: readonly PositionPoint[]
}

export function buildPositionSeries(rows: readonly PositionAccuracy[]): readonly PositionSeries[] {
  const byMethod = new Map<MethodName, PositionAccuracy[]>()
  for (const row of rows) {
    const existing = byMethod.get(row.method)
    byMethod.set(row.method, existing ? [...existing, row] : [row])
  }
  return METHOD_ORDER.filter((method) => byMethod.has(method)).map((method) => {
    const rowsForMethod = byMethod.get(method) ?? []
    const points = POSITION_ORDER.flatMap((position) => {
      const row = rowsForMethod.find((candidate) => candidate.position === position)
      if (!row) return []
      return [
        {
          position,
          accuracy: row.accuracy,
          n: row.n,
          interval: wilsonInterval(row.accuracy, row.n),
        },
      ]
    })
    return { method, points }
  })
}

/**
 * The drawn range, taken from the CI envelope with a 10% pad on each side. A
 * fixed floor left ~85% of the plot empty when every band sat in a few points
 * of each other.
 */
const ENVELOPE_PAD = 0.1

export interface PositionDomain {
  readonly min: number
  readonly max: number
}

export function positionDomain(series: readonly PositionSeries[]): PositionDomain {
  const bounds = series.flatMap((entry) =>
    entry.points.flatMap((point) => [
      point.interval?.low ?? point.accuracy,
      point.interval?.high ?? point.accuracy,
    ]),
  )
  if (bounds.length === 0) return { min: 0, max: 1 }
  const low = Math.min(...bounds)
  const high = Math.max(...bounds)
  const pad = Math.max((high - low) * ENVELOPE_PAD, 0.01)
  return { min: Math.max(0, low - pad), max: Math.min(1, high + pad) }
}
