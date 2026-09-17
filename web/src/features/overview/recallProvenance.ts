import type { RecallPoint } from './api'

/**
 * Where the recall@m curve stops being a measurement.
 *
 * Up to `measured_to_m` every shortlist was replayed and confirmed. Past it the
 * curve is the judge's own ranking, extended — nobody re-ran those steps, so
 * those points are a claim about the judge's ordering, not about what the agent
 * actually did. Drawing the two as the same kind of point would present an
 * untested ranking as evidence, so the curve splits here and the two halves are
 * drawn differently.
 */
export interface RecallSplit {
  /** Replay-confirmed: `m <= measuredToM`. */
  readonly measured: readonly RecallPoint[]
  /**
   * Judge ranking only: `m >= measuredToM`. It repeats the boundary point so
   * the two drawn segments meet rather than leaving a gap exactly where the
   * evidence changes kind.
   */
  readonly ranked: readonly RecallPoint[]
}

export function splitRecall(points: readonly RecallPoint[], measuredToM: number): RecallSplit {
  const measured = points.filter((point) => point.m <= measuredToM)
  const beyond = points.filter((point) => point.m > measuredToM)
  const boundary = measured.at(-1)
  return {
    measured,
    ranked: boundary ? [boundary, ...beyond] : beyond,
  }
}
