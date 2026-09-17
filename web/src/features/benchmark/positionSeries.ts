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

/** Lowest drawn value across every band, so the y-axis is not forced to zero. */
export function positionDomainMin(series: readonly PositionSeries[]): number {
  const lows = series.flatMap((entry) =>
    entry.points.map((point) => point.interval?.low ?? point.accuracy),
  )
  if (lows.length === 0) return 0
  return Math.max(0, Math.floor(Math.min(...lows) * 20) / 20)
}
