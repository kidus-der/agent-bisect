import { motion, useReducedMotion } from 'motion/react'

import { cn } from '@/lib/utils'

const PULSE_SECONDS = 1.6

interface ActivityPulseProps {
  readonly count: number
  readonly className?: string
}

/** A measurement-cyan dot that breathes while jobs are in flight. */
export function ActivityPulse({ count, className }: ActivityPulseProps) {
  const reduced = useReducedMotion() ?? false
  if (count === 0) return null
  return (
    <span className={cn('inline-flex items-center', className)}>
      <motion.span
        aria-hidden="true"
        className="size-1.5 rounded-pill bg-measure"
        animate={reduced ? { opacity: 1 } : { opacity: [1, 0.3, 1] }}
        transition={
          reduced
            ? { duration: 0 }
            : { duration: PULSE_SECONDS, repeat: Number.POSITIVE_INFINITY, ease: 'easeInOut' }
        }
      />
      <span className="sr-only">
        {count} {count === 1 ? 'job' : 'jobs'} running
      </span>
    </span>
  )
}
