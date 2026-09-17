import { Pause, Play } from 'lucide-react'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { BlameBadge } from '@/components/primitives/BlameBadge'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { Panel } from '@/components/primitives/Panel'
import { TapeStep, type TapeStepState } from '@/components/primitives/TapeStep'
import { STAGGER_SECONDS, springTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

import {
  REWIND_INTERVENTION,
  REWIND_RERUNS,
  REWIND_STEP_COUNT,
  REWIND_TARGET_STEP,
  REWIND_VERDICT,
  type RewindFrame,
  buildRewindFrames,
} from './rewindFrames'

const BLAMED_SCALE = 1.08
const IN_VIEW_AMOUNT = 0.35
const REPLAY_SPAN = REWIND_STEP_COUNT - REWIND_TARGET_STEP + 1

const DESCRIPTION =
  `Illustration of one bisect. A ${REWIND_STEP_COUNT}-step run is recorded live and fails at step ${REWIND_STEP_COUNT}. ` +
  `Bisect rewinds to step ${REWIND_TARGET_STEP}: steps 1 to ${REWIND_TARGET_STEP - 1} are read from tape with 0 calls, ` +
  `the tool result at step ${REWIND_TARGET_STEP} is replaced (${REWIND_INTERVENTION.before} to ${REWIND_INTERVENTION.after}), ` +
  `and steps ${REWIND_TARGET_STEP + 1} to ${REWIND_STEP_COUNT} re-run live ${REWIND_RERUNS} times. The run now passes. ` +
  `Blame: step ${REWIND_VERDICT.step}, effect +${REWIND_VERDICT.effect}, 95% interval ${REWIND_VERDICT.low} to ${REWIND_VERDICT.high}.`

interface StepCellProps {
  readonly step: number
  readonly state: TapeStepState
  readonly reduced: boolean
}

function StepCell({ step, state, reduced }: StepCellProps) {
  const fromTape = state === 'tape'
  const transition = {
    ...springTransition(fromTape ? 'drift' : state === 'blamed' ? 'settle' : 'snap', reduced),
    delay: fromTape && !reduced ? (step - 1) * STAGGER_SECONDS.rewind : 0,
  }
  return (
    <motion.div
      // Re-mount on state change so each new state pops in; colour itself never tweens.
      key={state}
      initial={reduced ? false : { opacity: 0.25, scale: 0.9 }}
      animate={{
        opacity: state === 'pending' ? 0.55 : 1,
        scale: state === 'blamed' ? BLAMED_SCALE : 1,
      }}
      transition={transition}
      className={cn('px-0.5', state === 'blamed' && 'relative z-10')}
    >
      <TapeStep step={step} state={state} size="fluid" />
    </motion.div>
  )
}

interface BandProps {
  readonly visible: boolean
  readonly className: string
  readonly children: React.ReactNode
}

/** A measurement bracket under a span of steps. */
function Band({ visible, className, children }: BandProps) {
  return (
    <div
      className={cn(
        'mx-0.5 h-5 truncate border-x border-b border-line-strong px-1 pt-1 text-center font-mono text-[10px] leading-none tracking-wide text-ink-muted uppercase sm:text-[11px]',
        visible ? 'opacity-100' : 'opacity-0',
        className,
      )}
    >
      {children}
    </div>
  )
}

interface TrackProps {
  readonly frame: RewindFrame
  readonly reduced: boolean
}

function Track({ frame, reduced }: TrackProps) {
  const rewinding = frame.phase === 'rewind'
  const playheadTransition = springTransition(rewinding ? 'drift' : 'settle', reduced)
  const replayProgress = frame.showIntervention
    ? (frame.playhead - REWIND_TARGET_STEP + 1) / REPLAY_SPAN
    : 0
  return (
    <div className="relative pt-5">
      {/* Clipped layer: the translated playhead wrapper must never widen the page. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-5 overflow-hidden">
        <motion.div
          className="absolute inset-0"
          initial={false}
          animate={{ x: `${((frame.playhead - 1) / REWIND_STEP_COUNT) * 100}%` }}
          transition={playheadTransition}
        >
          <div className="absolute top-0 bottom-0 left-[calc(100%/24)] flex -translate-x-1/2 flex-col items-center">
            <span className="num text-[10px] leading-none font-medium text-measure">
              k={frame.playhead}
            </span>
            {/* The playhead stops at the cell's top edge; it never crosses the step's own mark. */}
            <svg viewBox="0 0 8 6" className="mt-1 h-1.5 w-2 fill-current text-measure">
              <path d="M0 0h8L4 6z" />
            </svg>
          </div>
        </motion.div>
      </div>
      <div className="grid grid-cols-12">
        {frame.steps.map((state, index) => (
          <StepCell key={index + 1} step={index + 1} state={state} reduced={reduced} />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-12">
        <motion.div
          className="col-span-6 col-start-7 mx-0.5 h-0.5 origin-left bg-measure"
          initial={false}
          animate={{ scaleX: replayProgress }}
          transition={springTransition('drift', reduced)}
        />
      </div>
    </div>
  )
}

interface ReadoutProps {
  readonly frame: RewindFrame
}

function Readout({ frame }: ReadoutProps) {
  if (frame.phase === 'verdict') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <PassFailPill outcome="pass" size="sm" />
        <BlameBadge
          step={REWIND_VERDICT.step}
          effect={REWIND_VERDICT.effect}
          interval={[REWIND_VERDICT.low, REWIND_VERDICT.high]}
        />
      </div>
    )
  }
  return <span className="font-mono text-small text-ink">{frame.status}</span>
}

/** The signature moment as a working prototype. Loops, pauses offscreen, honours reduced motion. */
export function RewindLoop() {
  const frames = useMemo(() => buildRewindFrames(), [])
  const lastIndex = frames.length - 1
  const reduced = useReducedMotion() ?? false
  const containerRef = useRef<HTMLDivElement | null>(null)
  const inView = useInView(containerRef, { amount: IN_VIEW_AMOUNT })
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)

  const frameIndex = reduced ? lastIndex : index
  const frame = frames[frameIndex]
  const running = !reduced && !paused && inView

  useEffect(() => {
    if (!running || !frame) return undefined
    const timer = window.setTimeout(
      () => setIndex((current) => (current + 1) % frames.length),
      frame.holdMs,
    )
    return () => window.clearTimeout(timer)
  }, [running, frame, frames.length])

  if (!frame) return null
  const PauseIcon = paused ? Play : Pause

  return (
    <Panel
      variant="canvas"
      label="rewind · illustration"
      actions={
        reduced ? null : (
          <button
            type="button"
            onClick={() => setPaused((current) => !current)}
            aria-pressed={paused}
            className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-control border border-line-strong bg-surface px-2.5 text-small text-ink-muted hover:text-ink"
          >
            <PauseIcon aria-hidden="true" className="size-3.5" />
            {paused ? 'Play' : 'Pause'}
          </button>
        )
      }
    >
      <p className="sr-only">{DESCRIPTION}</p>
      <div ref={containerRef} aria-hidden="true" data-phase={frame.phase} data-testid="rewind-loop">
        <Track frame={frame} reduced={reduced} />
        <div className="mt-1 grid grid-cols-12">
          <Band visible={frame.showTapeBand} className="col-span-6">
            <span className="sm:hidden">tape · 0 calls</span>
            <span className="hidden sm:inline">read from tape · 0 calls</span>
          </Band>
          <div className="col-span-1" />
          <Band visible={frame.showRerunBand} className="col-span-5">
            re-run live × {REWIND_RERUNS}
          </Band>
        </div>
        <p
          className={cn(
            'mt-3 flex min-h-5 flex-wrap items-center gap-x-2 font-mono text-small text-ink',
            frame.showIntervention ? 'opacity-100' : 'opacity-0',
          )}
        >
          <span className="font-medium text-blame">step {REWIND_TARGET_STEP}</span>
          <span className="text-ink-muted">tool result replaced</span>
          <span>
            <span className="text-ink-muted line-through">{REWIND_INTERVENTION.before}</span>
            {' → '}
            <span className="font-medium text-ink">{REWIND_INTERVENTION.after}</span>
          </span>
        </p>
        <div className="mt-4 flex min-h-10 items-center border-t border-line pt-3">
          <Readout frame={frame} />
        </div>
      </div>
    </Panel>
  )
}
