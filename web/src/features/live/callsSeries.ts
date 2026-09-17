/**
 * `calls_series` arrives as one flat list of (timestamp, model, rate) rows.
 * The live line wants one ordered series per model, in unix seconds.
 */
import type { CallsPoint } from './api'

export interface SeriesPoint {
  /** Unix seconds. */
  readonly time: number
  readonly value: number
}

export interface ModelSeries {
  readonly model: string
  readonly points: readonly SeriesPoint[]
  readonly latest: number
  readonly peak: number
}

const MS_PER_SECOND = 1000

export function buildModelSeries(rows: readonly CallsPoint[]): readonly ModelSeries[] {
  const byModel = new Map<string, CallsPoint[]>()
  for (const row of rows) {
    const existing = byModel.get(row.model)
    byModel.set(row.model, existing ? [...existing, row] : [row])
  }
  return [...byModel.entries()]
    .map(([model, modelRows]) => {
      const points = modelRows
        .map((row) => ({
          time: Date.parse(row.ts) / MS_PER_SECOND,
          value: row.calls_per_minute,
        }))
        .filter((point) => Number.isFinite(point.time))
        .sort((a, b) => a.time - b.time)
      return {
        model,
        points,
        latest: points.at(-1)?.value ?? 0,
        peak: points.reduce((largest, point) => Math.max(largest, point.value), 0),
      }
    })
    .sort((a, b) => b.latest - a.latest)
}

/**
 * One y-domain for every trace on the page, rounded up to a readable step, so
 * two traces drawn side by side can be compared by eye rather than by label.
 */
export function sharedDomainMax(series: readonly ModelSeries[], step = 10): number {
  const peak = series.reduce((largest, entry) => Math.max(largest, entry.peak), 0)
  return Math.max(step, Math.ceil(peak / step) * step)
}

/** Seconds covered by the series, so the chart window matches the data it has. */
export function seriesWindowSeconds(series: readonly ModelSeries[], fallback: number): number {
  const spans = series.flatMap((entry) => {
    const first = entry.points[0]?.time
    const last = entry.points.at(-1)?.time
    return first === undefined || last === undefined ? [] : [last - first]
  })
  const widest = Math.max(0, ...spans)
  return widest > 0 ? widest : fallback
}

/** A short, stable display name for a provider model id. */
export function shortModelName(model: string): string {
  return model.split('/').at(-1) ?? model
}
