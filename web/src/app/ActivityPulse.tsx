import { useQuery } from '@tanstack/react-query'
import { motion, useReducedMotion } from 'motion/react'

import { type Schemas, apiFetch } from '@/api/client'
import { isNotAvailable } from '@/api/payload'
import { cn } from '@/lib/utils'

type LiveSnapshot = Readonly<Schemas['LiveSnapshot']>

/** Slow enough to be a nav badge rather than a second live feed. */
const POLL_INTERVAL_MS = 20_000
const PULSE_SECONDS = 1.6

/**
 * Whether any job is running. Polled, not streamed: the badge has to be right
 * on every page, and a second SSE connection for a 6px dot is not worth it.
 */
export function useRunningJobCount(): number {
  const query = useQuery({
    queryKey: ['live', 'running-jobs'],
    queryFn: ({ signal }) => apiFetch<LiveSnapshot>('/live/snapshot', { signal }),
    refetchInterval: POLL_INTERVAL_MS,
    retry: false,
  })
  const data = query.data?.data
  if (!data || isNotAvailable(data)) return 0
  // A badge must never be the thing that breaks the shell, so the payload is
  // checked rather than trusted: an older server may not send `jobs` at all.
  if (!Array.isArray(data.jobs)) return 0
  return data.jobs.filter((job) => job.state === 'running').length
}

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
