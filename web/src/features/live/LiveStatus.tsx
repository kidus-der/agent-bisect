import { motion, useReducedMotion } from 'motion/react'

import { cn } from '@/lib/utils'

import { formatAge } from './eventGroups'
import type { LiveConnectionState } from './useLiveStream'

interface StatusCopy {
  readonly label: string
  readonly dot: string
  readonly text: string
  readonly border: string
  readonly pulse: boolean
}

const STATUS: Readonly<Record<LiveConnectionState, StatusCopy>> = {
  connecting: {
    label: 'connecting',
    dot: 'bg-ink-muted',
    text: 'text-ink-muted',
    border: 'border-line-strong',
    pulse: true,
  },
  live: {
    label: 'live',
    dot: 'bg-measure',
    text: 'text-measure',
    border: 'border-measure/40',
    pulse: true,
  },
  reconnecting: {
    label: 'reconnecting',
    dot: 'bg-ink-muted',
    text: 'text-ink',
    border: 'border-line-strong',
    pulse: true,
  },
  offline: {
    label: 'offline',
    dot: 'bg-fail',
    text: 'text-fail',
    border: 'border-fail/40',
    pulse: false,
  },
  paused: {
    label: 'paused · tab hidden',
    dot: 'bg-tape',
    text: 'text-ink-muted',
    border: 'border-line-strong',
    pulse: false,
  },
}

const PULSE_SECONDS = 1.6

interface LiveStatusProps {
  readonly connection: LiveConnectionState
  readonly updates: number
  /** When the newest frame arrived, and the clock to measure it against. */
  readonly lastFrameAt: number | null
  readonly now: number
  readonly onRetry: () => void
}

/**
 * The connection itself, stated. Every state carries its word, so the dot is
 * decoration rather than the message; only `offline` spends a semantic colour
 * (fail), because amber means blame and nothing else (§3, principle 2).
 */
export function LiveStatus({ connection, updates, lastFrameAt, now, onRetry }: LiveStatusProps) {
  const reduced = useReducedMotion() ?? false
  const status = STATUS[connection]
  const animate = status.pulse && !reduced
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        className={cn(
          'inline-flex items-center gap-2 rounded-pill border bg-surface px-2.5 py-1 label-instrument',
          status.border,
          status.text,
        )}
      >
        <motion.span
          aria-hidden="true"
          className={cn('size-2 rounded-pill', status.dot)}
          animate={animate ? { opacity: [1, 0.25, 1] } : { opacity: 1 }}
          transition={
            animate
              ? { duration: PULSE_SECONDS, repeat: Number.POSITIVE_INFINITY, ease: 'easeInOut' }
              : { duration: 0 }
          }
        />
        {status.label}
      </span>
      <span className="num text-[12px] text-ink-muted" aria-live="off">
        {updates} {updates === 1 ? 'update' : 'updates'}
        {/* The count alone cannot show a stalled stream; the age can. */}
        {lastFrameAt === null ? '' : ` · ${formatAge(new Date(lastFrameAt).toISOString(), now)}`}
      </span>
      {connection === 'offline' || connection === 'reconnecting' ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-7 items-center rounded-control border border-line-strong bg-elevated px-2.5 text-small text-ink"
        >
          Retry now
        </button>
      ) : null}
      <span role="status" className="sr-only">
        Live connection {status.label}. {updates} updates received
        {lastFrameAt === null
          ? ''
          : `, newest ${formatAge(new Date(lastFrameAt).toISOString(), now)}`}
        .
      </span>
    </div>
  )
}
