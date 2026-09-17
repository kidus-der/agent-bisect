/**
 * Motion system. Springs only, transform/opacity only. With reduced motion every
 * helper here collapses to an instant state change (duration 0, no stagger).
 * Presets are direction.md §4.
 */
import { type Transition, type Variants, animate, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useRef } from 'react'

export interface SpringPreset {
  readonly stiffness: number
  readonly damping: number
  readonly mass: number
}

export const springs = {
  /** Button press, toggle, badge pop. */
  snap: { stiffness: 500, damping: 34, mass: 0.7 },
  /** Card/list-item enter, hover lift. */
  settle: { stiffness: 260, damping: 28, mass: 1 },
  /** Shared-layout list -> detail transition. */
  glide: { stiffness: 160, damping: 22, mass: 1.1 },
  /** Rewind fade/replay sequencing, large timeline moves. */
  drift: { stiffness: 90, damping: 18, mass: 1.3 },
  /** Number ticker counting, chart value morph. */
  ticker: { stiffness: 210, damping: 26, mass: 0.9 },
} as const satisfies Record<string, SpringPreset>

export type SpringName = keyof typeof springs

export const INSTANT: Transition = { duration: 0 }

export const STAGGER_SECONDS = {
  rewind: 0.04,
  forest: 0.06,
  list: 0.03,
} as const

/**
 * How long a chart above the fold waits before it starts entering.
 *
 * The page itself fades and lifts in on a spring when the route changes, and a
 * chart that draws itself during that move is two animations fighting over the
 * same pixels — the chart reads as already settled by the time the page lands.
 * Waiting for the page to arrive first makes the entrance its own event.
 */
export const ENTRANCE_LEAD_IN_SECONDS = 0.28

export function springTransition(name: SpringName, reduced: boolean): Transition {
  return reduced ? INSTANT : { type: 'spring', ...springs[name] }
}

/** A named spring, delayed — instant and undelayed under reduced motion. */
export function delayedSpring(name: SpringName, reduced: boolean, delay: number): Transition {
  return reduced ? INSTANT : { ...springTransition(name, reduced), delay }
}

/** The transition for a named spring, or an instant change under reduced motion. */
export function useSpringTransition(name: SpringName): Transition {
  const reduced = useReducedMotion() ?? false
  return useMemo(() => springTransition(name, reduced), [name, reduced])
}

export interface StaggerVariants {
  readonly container: Variants
  readonly item: Variants
}

const ENTER_OFFSET_PX = 8

export function staggerVariants(
  name: SpringName,
  staggerSeconds: number,
  reduced: boolean,
): StaggerVariants {
  if (reduced) {
    return {
      container: { hidden: {}, shown: { transition: INSTANT } },
      item: { hidden: { opacity: 1, y: 0 }, shown: { opacity: 1, y: 0, transition: INSTANT } },
    }
  }
  return {
    container: { hidden: {}, shown: { transition: { staggerChildren: staggerSeconds } } },
    item: {
      hidden: { opacity: 0, y: ENTER_OFFSET_PX },
      shown: { opacity: 1, y: 0, transition: springTransition(name, false) },
    },
  }
}

/** Parent/child variants for a staggered enter; use with initial="hidden" animate="shown". */
export function useStagger(
  name: SpringName = 'settle',
  staggerSeconds: number = STAGGER_SECONDS.list,
): StaggerVariants {
  const reduced = useReducedMotion() ?? false
  return useMemo(
    () => staggerVariants(name, staggerSeconds, reduced),
    [name, staggerSeconds, reduced],
  )
}

/**
 * Number ticker: springs a number towards `value` and writes formatted text into
 * the returned ref without re-rendering React. Reduced motion writes it once.
 */
export function useNumberTicker<T extends HTMLElement>(
  value: number,
  format: (current: number) => string,
  delaySeconds = 0,
  /**
   * Holds the number at its start until the caller says it is being looked at.
   * A ticker that runs on mount finishes behind the page's own enter animation,
   * so the number is already final by the time anyone can read it.
   */
  play = true,
): React.RefObject<T | null> {
  const ref = useRef<T | null>(null)
  const previous = useRef(0)
  const reduced = useReducedMotion() ?? false

  useEffect(() => {
    const node = ref.current
    if (!node) return undefined
    if (reduced) {
      node.textContent = format(value)
      previous.current = value
      return undefined
    }
    if (!play) {
      node.textContent = format(previous.current)
      return undefined
    }
    const controls = animate(previous.current, value, {
      type: 'spring',
      ...springs.ticker,
      delay: delaySeconds,
      onUpdate: (current) => {
        node.textContent = format(current)
      },
      onComplete: () => {
        node.textContent = format(value)
      },
    })
    previous.current = value
    return () => controls.stop()
  }, [value, format, reduced, delaySeconds, play])

  return ref
}

/** Shared-layout ids so list rows can morph into their detail-page equivalents. */
export const layoutIds = {
  /** The whole Runs row -> Run detail header morph target. */
  runRow: (runId: string): string => `run-row-${runId}`,
  runIdChip: (runId: string): string => `run-${runId}-id`,
  runBlameStripe: (runId: string): string => `run-${runId}-blame-stripe`,
  runStatus: (runId: string): string => `run-${runId}-status`,
  navIndicator: 'nav-active-indicator',
  segmentIndicator: (groupId: string): string => `segment-${groupId}-indicator`,
  tabIndicator: (groupId: string): string => `tab-${groupId}-indicator`,
} as const
