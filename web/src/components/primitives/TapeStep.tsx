import { Check, Crosshair, Dot, type LucideIcon, Minus, Voicemail, X } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import { springs } from '@/design/motion'
import { cn } from '@/lib/utils'

import type { Actor } from './ActorGlyph'

export type TapeStepState = 'live' | 'ran' | 'tape' | 'blamed' | 'failed' | 'passed' | 'pending'
export type TapeStepSize = 'sm' | 'md' | 'fluid'

interface TapeStepProps {
  /** 1-based step index. */
  readonly step: number
  readonly state: TapeStepState
  readonly actor?: Actor
  readonly selected?: boolean
  /** `fluid` fills its grid column (the rewind illustration at 390px). */
  readonly size?: TapeStepSize
  readonly onSelect?: (step: number) => void
  readonly className?: string
}

const STATE_LABELS: Readonly<Record<TapeStepState, string>> = {
  live: 'running live',
  ran: 'ran live',
  tape: 'read from tape',
  blamed: 'blamed',
  failed: 'failed',
  passed: 'passed',
  pending: 'not run yet',
}

const STATE_STYLES: Readonly<Record<TapeStepState, string>> = {
  live: 'border-measure bg-measure-tint text-ink',
  ran: 'border-measure bg-surface text-ink',
  tape: 'border-tape bg-tape-tint text-ink-muted',
  blamed: 'border-transparent bg-blame-tint text-ink',
  failed: 'border-fail bg-fail-tint text-ink',
  passed: 'border-pass bg-pass-tint text-ink',
  pending: 'border-line-strong text-ink-muted border-dashed bg-transparent',
}

const STATE_MARKS: Readonly<Record<Exclude<TapeStepState, 'live'>, LucideIcon>> = {
  ran: Dot,
  tape: Voicemail,
  blamed: Crosshair,
  failed: X,
  passed: Check,
  pending: Minus,
}

const MARK_COLOURS: Readonly<Record<TapeStepState, string>> = {
  live: 'text-measure',
  ran: 'text-measure',
  tape: 'text-ink-muted',
  blamed: 'text-blame',
  failed: 'text-fail',
  passed: 'text-pass',
  pending: 'text-ink-muted',
}

function LiveDot() {
  const reduced = useReducedMotion() ?? false
  return (
    <motion.span
      aria-hidden="true"
      className="block size-1.5 rounded-full bg-measure"
      animate={reduced ? undefined : { opacity: 0.3 }}
      transition={
        reduced
          ? undefined
          : { type: 'spring', ...springs.drift, repeat: Infinity, repeatType: 'mirror' }
      }
    />
  )
}

/** One cell of the tape. Square-ish (4px) on purpose: instrument, not card. */
const SIZE_STYLES: Readonly<Record<TapeStepSize, string>> = {
  sm: 'h-9 w-7',
  md: 'h-12 w-10',
  fluid: 'h-10 w-full sm:h-12',
}

export function TapeStep({
  step,
  state,
  actor,
  selected = false,
  size = 'md',
  onSelect,
  className,
}: TapeStepProps) {
  const Mark = state === 'live' ? null : STATE_MARKS[state]
  const name = `Step ${step}${actor ? `, ${actor}` : ''}, ${STATE_LABELS[state]}`
  const body = (
    <span
      className={cn(
        'flex flex-col items-center justify-between rounded-step border py-1.5',
        SIZE_STYLES[size],
        STATE_STYLES[state],
        selected && 'outline-2 outline-offset-2 outline-focus',
      )}
    >
      <span className="num text-small leading-none font-medium">{step}</span>
      <span className={cn('flex h-3.5 items-center', MARK_COLOURS[state])}>
        {Mark ? <Mark aria-hidden="true" className="size-3.5" strokeWidth={2.5} /> : <LiveDot />}
      </span>
    </span>
  )
  const frame = cn(
    'shrink-0 rounded-step p-px',
    size === 'fluid' ? 'flex w-full' : 'inline-flex',
    state === 'blamed' && 'blame-gradient shadow-glow-blame',
    className,
  )
  if (!onSelect) {
    return (
      <span role="img" aria-label={name} data-state={state} className={frame}>
        {body}
      </span>
    )
  }
  return (
    <button
      type="button"
      aria-label={name}
      aria-pressed={selected}
      data-state={state}
      onClick={() => onSelect(step)}
      className={cn(frame, 'cursor-pointer')}
    >
      {body}
    </button>
  )
}
