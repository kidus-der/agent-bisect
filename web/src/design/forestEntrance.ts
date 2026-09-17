/**
 * Signature moment §7.3, as one definition.
 *
 * "Rows enter top-to-bottom, 60ms stagger; each whisker draws outward from the
 * point estimate (`settle`), then the dot pops in with a small overshoot. The
 * blamed row is amber and enters last — reads as 'found', not 'one of many'."
 *
 * Two forest plots now exist — the run's per-step plot and the gate history
 * across pull requests — and a signature moment that differs between them is
 * not a signature. Under reduced motion every helper here returns the final
 * state with no transition.
 */
import type { Transition } from 'motion/react'

import { STAGGER_SECONDS, springTransition } from './motion'

/** The dot lands just after its whisker has finished drawing. */
export const FOREST_DOT_LAG_SECONDS = 0.06

export interface ForestRowTiming {
  readonly index: number
  readonly total: number
  /**
   * True for the row that should arrive last whatever its position — the
   * blamed step, or the flagged check. It reads as "found".
   */
  readonly deferred?: boolean
  readonly reduced: boolean
}

/** When a row's whisker starts drawing. */
export function forestRowDelay({ index, total, deferred, reduced }: ForestRowTiming): number {
  if (reduced) return 0
  if (deferred) return Math.max(total - 1, 0) * STAGGER_SECONDS.forest + STAGGER_SECONDS.forest
  return index * STAGGER_SECONDS.forest
}

export interface ForestMotion {
  /** `false` under reduced motion: motion skips the initial state entirely. */
  readonly initial: false | Record<string, number>
  readonly animate: Record<string, number>
  readonly transition: Transition
}

/** The interval, drawing outward from the estimate. */
export function forestWhiskerMotion(delay: number, reduced: boolean): ForestMotion {
  return {
    initial: reduced ? false : { scaleX: 0 },
    animate: { scaleX: 1 },
    transition: { ...springTransition('settle', reduced), delay: reduced ? 0 : delay },
  }
}

/** The point estimate, popping in once its interval is drawn. */
export function forestDotMotion(delay: number, reduced: boolean): ForestMotion {
  return {
    initial: reduced ? false : { scale: 0 },
    animate: { scale: 1 },
    transition: {
      ...springTransition('settle', reduced),
      delay: reduced ? 0 : delay + FOREST_DOT_LAG_SECONDS,
    },
  }
}
