import { Link } from '@tanstack/react-router'
import { ArrowUpRight, Pause, Play } from 'lucide-react'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'

import { BlameBadge } from '@/components/primitives/BlameBadge'
import { Panel } from '@/components/primitives/Panel'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { TapeStep, type TapeStepState } from '@/components/primitives/TapeStep'
import { springTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

import {
  DEFAULT_REWIND_SPEC,
  type RewindFrame,
  type RewindSpec,
  buildRewindFrames,
} from './rewindFrames'

const BLAMED_SCALE = 1.06
const IN_VIEW_AMOUNT = 0.35
/** Cells stay instrument-sized: a 12-step tape must not become twelve wide slabs at 1440. */
const MAX_CELL_PX = 48

/** Opacity is the only channel that moves, so the desaturation costs no layout. */
const STATE_OPACITY: Readonly<Record<TapeStepState, number>> = {
  live: 1,
  ran: 1,
  tape: 0.7,
  blamed: 1,
  failed: 1,
  passed: 1,
  pending: 0.45,
}

function describeSpec(spec: RewindSpec, runLabel: string): string {
  const { stepCount, targetStep, reruns, intervention, verdict } = spec
  const replaced = intervention
    ? `the tool result at step ${targetStep} is replaced (${intervention.before} to ${intervention.after})`
    : `the tool result at step ${targetStep} is replaced`
  const blame = verdict
    ? ` Blame: step ${verdict.step}, effect ${verdict.effect.toFixed(2)}, 95% interval ${verdict.low.toFixed(2)} to ${verdict.high.toFixed(2)}.`
    : ` The decisive step is ${targetStep}; no effect estimate was reported for it.`
  return (
    `${runLabel}: a ${stepCount}-step run is recorded live and fails at step ${stepCount}. ` +
    `Bisect rewinds to step ${targetStep}: steps 1 to ${targetStep - 1} are read from tape with 0 calls, ` +
    `${replaced}, and steps ${targetStep + 1} to ${stepCount} re-run live ${reruns} times. ` +
    `The run now passes.${blame}`
  )
}

interface StepCellProps {
  readonly step: number
  readonly state: TapeStepState
  readonly reduced: boolean
}

function StepCell({ step, state, reduced }: StepCellProps) {
  return (
    <motion.div
      initial={false}
      animate={{
        opacity: STATE_OPACITY[state],
        scale: state === 'blamed' ? BLAMED_SCALE : 1,
      }}
      transition={springTransition(state === 'blamed' ? 'settle' : 'drift', reduced)}
      className={cn('px-0.5', state === 'blamed' && 'relative z-10')}
    >
      <TapeStep step={step} state={state} size="fluid" />
    </motion.div>
  )
}

interface BandProps {
  readonly visible: boolean
  readonly span: number
  readonly start: number
  readonly children: ReactNode
}

/** A measurement bracket under a span of steps. */
function Band({ visible, span, start, children }: BandProps) {
  if (span <= 0) return null
  return (
    <div
      style={{ gridColumn: `${start} / span ${span}` }}
      className={cn(
        'mx-0.5 h-5 truncate border-x border-b border-line-strong px-1 pt-1 text-center font-mono text-[10px] leading-none tracking-wide text-ink-muted uppercase sm:text-[11px]',
        visible ? 'opacity-100' : 'opacity-0',
      )}
    >
      {children}
    </div>
  )
}

interface TrackProps {
  readonly frame: RewindFrame
  readonly spec: RewindSpec
  readonly reduced: boolean
}

function Track({ frame, spec, reduced }: TrackProps) {
  const { stepCount, targetStep } = spec
  const columns = `repeat(${stepCount}, minmax(0, 1fr))`
  const tailSpan = stepCount - targetStep
  const replayProgress =
    frame.showIntervention && tailSpan > 0
      ? Math.min(1, Math.max(0, (frame.playhead - targetStep) / tailSpan))
      : 0
  const rewindProgress = frame.rewoundThrough / Math.max(targetStep - 1, 1)

  return (
    <div className="relative pt-5">
      {/* Clipped layer: the translated playhead wrapper must never widen the page. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-5 overflow-hidden">
        <motion.div
          className="absolute inset-0"
          initial={false}
          animate={{ x: `${((frame.playhead - 1) / stepCount) * 100}%` }}
          transition={springTransition(frame.phase === 'rewind' ? 'drift' : 'settle', reduced)}
        >
          <div
            style={{ left: `calc(100% / ${stepCount * 2})` }}
            className="absolute top-0 bottom-0 flex -translate-x-1/2 flex-col items-center"
          >
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

      <div className="grid" style={{ gridTemplateColumns: columns }}>
        {frame.steps.map((state, index) => (
          <StepCell key={index + 1} step={index + 1} state={state} reduced={reduced} />
        ))}
      </div>

      {/* One lane, two meanings: slate sweeping back to tape, cyan replaying forward. */}
      <div className="mt-2 grid" style={{ gridTemplateColumns: columns }}>
        <motion.div
          style={{ gridColumn: `1 / span ${Math.max(targetStep - 1, 1)}` }}
          className="mx-0.5 h-0.5 origin-left bg-tape"
          initial={false}
          animate={{ scaleX: frame.phase === 'rewind' ? rewindProgress : 0 }}
          transition={springTransition('drift', reduced)}
        />
        {tailSpan > 0 ? (
          <motion.div
            style={{ gridColumn: `${targetStep + 1} / span ${tailSpan}` }}
            className="mx-0.5 h-0.5 origin-left bg-measure"
            initial={false}
            animate={{ scaleX: replayProgress }}
            transition={springTransition('drift', reduced)}
          />
        ) : null}
      </div>

      <div className="mt-1 grid" style={{ gridTemplateColumns: columns }}>
        <Band visible={frame.showTapeBand} start={1} span={targetStep - 1}>
          <span className="sm:hidden">tape · 0 calls</span>
          <span className="hidden sm:inline">read from tape · 0 calls</span>
        </Band>
        <Band visible={frame.showRerunBand} start={targetStep + 1} span={tailSpan}>
          re-run live × {spec.reruns}
        </Band>
      </div>
    </div>
  )
}

interface ReadoutProps {
  readonly frame: RewindFrame
  readonly spec: RewindSpec
}

function Readout({ frame, spec }: ReadoutProps) {
  if (frame.phase !== 'verdict') {
    return <span className="font-mono text-small text-ink">{frame.status}</span>
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <PassFailPill outcome="pass" size="sm" />
      {spec.verdict ? (
        <BlameBadge
          step={spec.verdict.step}
          effect={spec.verdict.effect}
          interval={[spec.verdict.low, spec.verdict.high]}
        />
      ) : (
        // Blame is never shown with a number the API did not report.
        <span className="font-mono text-small text-ink-muted">
          decisive step {spec.targetStep} · no effect reported
        </span>
      )}
    </div>
  )
}

export interface RewindLoopProps {
  /** The run to play. Defaults to the brief's twelve-step illustration. */
  readonly spec?: RewindSpec
  readonly label?: string
  /** Text alternative; defaults to one generated from the spec. */
  readonly description?: string
  /** Route for the run this plays, making the tape a link to its detail page. */
  readonly href?: string
  /** Name of the run, used in the link and the text alternative. */
  readonly runLabel?: string
}

/** The signature moment. Loops, pauses offscreen, honours reduced motion. */
export function RewindLoop({
  spec = DEFAULT_REWIND_SPEC,
  label = 'rewind · illustration',
  description,
  href,
  runLabel = 'Illustration of one bisect',
}: RewindLoopProps) {
  const frames = useMemo(() => buildRewindFrames(spec), [spec])
  const lastIndex = frames.length - 1
  const reduced = useReducedMotion() ?? false
  const containerRef = useRef<HTMLDivElement | null>(null)
  const inView = useInView(containerRef, { amount: IN_VIEW_AMOUNT })
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)

  const frameIndex = reduced ? lastIndex : Math.min(index, lastIndex)
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
  const text = description ?? describeSpec(spec, runLabel)
  const tape = (
    <div ref={containerRef} aria-hidden="true" data-phase={frame.phase} data-testid="rewind-loop">
      <Track frame={frame} spec={spec} reduced={reduced} />
    </div>
  )

  return (
    <Panel
      variant="canvas"
      label={label}
      actions={
        <div className="flex items-center gap-2">
          {href ? (
            <Link
              to={href}
              className="inline-flex h-8 items-center gap-1 rounded-control border border-line-strong bg-surface px-2.5 text-small text-ink-muted hover:text-ink"
            >
              Open run
              <ArrowUpRight aria-hidden="true" className="size-3.5" />
            </Link>
          ) : null}
          {reduced ? null : (
            <button
              type="button"
              onClick={() => setPaused((current) => !current)}
              aria-pressed={paused}
              className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-control border border-line-strong bg-surface px-2.5 text-small text-ink-muted hover:text-ink"
            >
              <PauseIcon aria-hidden="true" className="size-3.5" />
              {paused ? 'Play' : 'Pause'}
            </button>
          )}
        </div>
      }
    >
      <p className="sr-only">{text}</p>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start lg:gap-8">
        <div style={{ maxWidth: spec.stepCount * MAX_CELL_PX }} className="min-w-0">
          {href ? (
            <Link
              to={href}
              tabIndex={-1}
              aria-hidden="true"
              className="block rounded-step focus-visible:-outline-offset-2"
            >
              {tape}
            </Link>
          ) : (
            tape
          )}
        </div>
        <div aria-hidden="true" className="flex min-w-0 flex-col gap-3">
          <p
            className={cn(
              'flex min-h-5 flex-wrap items-center gap-x-2 font-mono text-small text-ink',
              frame.showIntervention ? 'opacity-100' : 'opacity-0',
            )}
          >
            <span className="font-medium text-blame">step {spec.targetStep}</span>
            <span className="text-ink-muted">tool result replaced</span>
            {spec.intervention ? (
              <span className="min-w-0 break-all">
                <span className="text-ink-muted line-through">{spec.intervention.before}</span>
                {' → '}
                <span className="font-medium text-ink">{spec.intervention.after}</span>
              </span>
            ) : null}
          </p>
          <div className="flex min-h-10 items-center border-t border-line pt-3">
            <Readout frame={frame} spec={spec} />
          </div>
        </div>
      </div>
    </Panel>
  )
}
