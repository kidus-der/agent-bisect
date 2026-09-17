/**
 * The pre-registered P5 bar (brief §9.8): Bisect's step accuracy must reach the
 * best judge's accuracy plus 15 points, fixed before any measurement.
 *
 * It is drawn as a reference marker on the method comparison, not as a bar of
 * its own, because it is a threshold rather than a measured value — and it is
 * reported even when it lands above 1.0, where no method could ever clear it.
 * Rewriting a pre-registered threshold after seeing the numbers is the thing the
 * pre-registration exists to prevent.
 */
import type { MethodResult } from './api'
import { methodMeta } from './methods'

export const PREREGISTERED_MARGIN = 0.15
export const MAX_ATTAINABLE_ACCURACY = 1

export interface PreregisteredBar {
  readonly bestJudge: MethodResult
  readonly bisect: MethodResult
  /** Best judge + 15 points. May exceed 1. */
  readonly threshold: number
  /** True when the threshold is above any attainable accuracy. */
  readonly unattainable: boolean
  readonly cleared: boolean
  /** Bisect's actual margin over the best judge, in rate units. */
  readonly marginOverBestJudge: number
}

function bestBy(
  methods: readonly MethodResult[],
  predicate: (result: MethodResult) => boolean,
): MethodResult | null {
  const candidates = methods.filter(predicate)
  if (candidates.length === 0) return null
  return candidates.reduce((best, candidate) =>
    candidate.accuracy.value > best.accuracy.value ? candidate : best,
  )
}

export function preregisteredBar(methods: readonly MethodResult[]): PreregisteredBar | null {
  const bestJudge = bestBy(methods, (result) => methodMeta(result.method).kind === 'judge')
  const bisect = methods.find((result) => result.method === 'bisect') ?? null
  if (!bestJudge || !bisect) return null

  const threshold = bestJudge.accuracy.value + PREREGISTERED_MARGIN
  return {
    bestJudge,
    bisect,
    threshold,
    unattainable: threshold > MAX_ATTAINABLE_ACCURACY,
    cleared: bisect.accuracy.value >= threshold,
    marginOverBestJudge: bisect.accuracy.value - bestJudge.accuracy.value,
  }
}
