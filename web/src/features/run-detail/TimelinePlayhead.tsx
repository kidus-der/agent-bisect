import { motion } from 'motion/react'

import { springTransition } from '@/design/motion'

import type { TimelineGeometry } from './timelineScale'

export const PLAYHEAD_HEIGHT = 20

interface TimelinePlayheadProps {
  readonly geometry: TimelineGeometry
  readonly step: number
  readonly reduced: boolean
  /** The one glow in this view sits on the playhead while a rewind is running. */
  readonly glowing: boolean
}

/** The scrub head. Rides the band scale, so it always lands on a cell centre. */
export function TimelinePlayhead({ geometry, step, reduced, glowing }: TimelinePlayheadProps) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none relative"
      style={{ width: geometry.contentWidth, height: PLAYHEAD_HEIGHT }}
    >
      <motion.div
        className="absolute top-0 bottom-0 left-0 flex flex-col items-center"
        style={{ width: geometry.bandWidth }}
        initial={false}
        animate={{ x: geometry.x(step) }}
        transition={springTransition('settle', reduced)}
      >
        <span className="num text-[10px] leading-none font-medium text-measure">k={step}</span>
        <svg
          viewBox="0 0 8 6"
          className="mt-1 h-1.5 w-2 fill-current text-measure"
          style={glowing ? { filter: 'drop-shadow(0 0 6px var(--bx-measure))' } : undefined}
        >
          <path d="M0 0h8L4 6z" />
        </svg>
      </motion.div>
    </div>
  )
}
