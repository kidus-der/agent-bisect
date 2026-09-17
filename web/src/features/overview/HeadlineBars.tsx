/**
 * The Overview's focal element: Bisect vs the best judge as horizontal bars,
 * each with its own 95% interval, and the gap between them at display size.
 * No estimate is drawn without its interval (direction.md §8).
 */
import { motion, useReducedMotion } from 'motion/react'
import { useCallback } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { springTransition, useNumberTicker } from '@/design/motion'
import { cn } from '@/lib/utils'
import { formatPercent, formatPoints } from '@/lib/stats'

import type { HeadlineResult } from './api'
import { type HeadlineBar, type HeadlineRole, headlineBars, headlineGap } from './headline'

const AXIS_TICKS = [0, 0.25, 0.5, 0.75, 1] as const
const BAR_DELAY_SECONDS = 0.09
const PERCENT_PRECISION = 4

/** Colour roles are fixed: cyan measures, violet is the judge. Amber is blame only. */
const ROLE_FILL: Readonly<Record<HeadlineRole, string>> = {
  measure: 'bg-measure',
  judge: 'bg-judge',
}
const ROLE_TEXT: Readonly<Record<HeadlineRole, string>> = {
  measure: 'text-measure',
  judge: 'text-judge',
}

function percent(value: number): string {
  return `${(value * 100).toFixed(PERCENT_PRECISION)}%`
}

interface TickingPercentProps {
  readonly value: number
  readonly className?: string
}

/** Springs to its value without re-rendering; assistive tech hears the final number once. */
function TickingPercent({ value, className }: TickingPercentProps) {
  const format = useCallback((current: number) => formatPercent(current), [])
  const ref = useNumberTicker<HTMLSpanElement>(value, format)
  return (
    <>
      <span className="sr-only">{formatPercent(value)}</span>
      <span ref={ref} aria-hidden="true" className={className}>
        {formatPercent(value)}
      </span>
    </>
  )
}

interface WhiskerProps {
  readonly bar: HeadlineBar
  readonly reduced: boolean
  readonly delay: number
}

const WHISKER_CAP_HALF = 6
const WHISKER_HALO_PX = 3.5

/**
 * The 95% interval, drawn *on the bar's centreline* rather than in a lane under
 * it — it is this bar's interval, not a separate rule. It crosses both the
 * filled and unfilled parts of the track, so each stroke is painted twice: once
 * wide in the panel's ground colour as a halo, once thin in ink on top. That
 * reads on the role fill and on the empty track, in both themes.
 */
function Whisker({ bar, reduced, delay }: WhiskerProps) {
  const transition = { ...springTransition('settle', reduced), delay: reduced ? 0 : delay }
  const marks = (
    <>
      <line x1={`${bar.low * 100}%`} x2={`${bar.high * 100}%`} y1="50%" y2="50%" />
      {[bar.low, bar.high].map((bound) => (
        <line
          key={bound}
          x1={`${bound * 100}%`}
          x2={`${bound * 100}%`}
          y1={`calc(50% - ${WHISKER_CAP_HALF}px)`}
          y2={`calc(50% + ${WHISKER_CAP_HALF}px)`}
        />
      ))}
    </>
  )
  return (
    <motion.svg
      aria-hidden="true"
      initial={reduced ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transition}
      className="pointer-events-none absolute inset-0 size-full"
      preserveAspectRatio="none"
    >
      <g stroke="var(--bx-ground)" strokeWidth={WHISKER_HALO_PX} strokeLinecap="butt">
        {marks}
      </g>
      <g stroke="var(--bx-text)" strokeWidth={1.5} strokeLinecap="butt">
        {marks}
      </g>
      <rect
        x={`calc(${bar.value * 100}% - 3px)`}
        y="calc(50% - 3px)"
        width={6}
        height={6}
        fill="var(--bx-text)"
        stroke="var(--bx-ground)"
        strokeWidth={1.5}
      />
    </motion.svg>
  )
}

interface BarRowProps {
  readonly bar: HeadlineBar
  readonly index: number
}

function BarRow({ bar, index }: BarRowProps) {
  const reduced = useReducedMotion() ?? false
  const delay = reduced ? 0 : index * BAR_DELAY_SECONDS
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        {/* The blueprint dots are texture, not something to read type through. */}
        <h3 className="bg-ground pr-2 text-h3 text-ink">{bar.label}</h3>
        <TickingPercent value={bar.value} className={cn('num text-stat', ROLE_TEXT[bar.role])} />
      </div>
      <div
        aria-hidden="true"
        className="relative h-8 overflow-hidden rounded-step border border-line bg-elevated sm:h-9"
      >
        <motion.span
          initial={reduced ? false : { scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ ...springTransition('settle', reduced), delay }}
          style={{ width: percent(bar.value) }}
          className={cn('absolute inset-y-0 left-0 origin-left', ROLE_FILL[bar.role])}
        />
        <Whisker bar={bar} reduced={reduced} delay={delay} />
      </div>
      <p className="w-fit bg-ground pr-2 num text-small text-ink-muted">
        95% CI {formatPercent(bar.low)} – {formatPercent(bar.high)}
      </p>
    </div>
  )
}

function Axis() {
  return (
    <div aria-hidden="true" className="relative mt-1 h-8 border-t border-line">
      {AXIS_TICKS.map((tick) => (
        <span
          key={tick}
          className="absolute top-0 flex -translate-x-1/2 flex-col items-center gap-1"
          style={{ left: percent(tick) }}
        >
          <span className="h-1.5 w-px bg-line-strong" />
          <span className="num text-[11px] text-ink-muted">{Math.round(tick * 100)}</span>
        </span>
      ))}
    </div>
  )
}

interface HeadlineBarsProps {
  readonly headline: HeadlineResult
  /** True when every number on screen came from a fixture, not a measurement. */
  readonly simulated: boolean
  /** How many labelled failures the accuracy was scored on, when known. */
  readonly sampleSize?: number | null
}

export function HeadlineBars({ headline, simulated, sampleSize }: HeadlineBarsProps) {
  const reduced = useReducedMotion() ?? false
  const bars = headlineBars(headline)
  const gap = headlineGap(headline)
  const gapFormat = useCallback((current: number) => formatPoints(current), [])
  const gapRef = useNumberTicker<HTMLSpanElement>(gap.points, gapFormat)

  return (
    <section
      aria-labelledby="headline-result"
      className="relative flex flex-col gap-6 border border-dashed border-line-strong bg-ground blueprint-dots p-5 sm:p-6 lg:p-8"
    >
      <header className="flex w-fit flex-col gap-3 bg-ground pr-3">
        <InstrumentLabel>
          {sampleSize == null
            ? 'result · step accuracy'
            : `result · step accuracy · n=${sampleSize}`}
        </InstrumentLabel>
        {/* The page's h1: the Overview leads with its result, not with its own name. */}
        <h1 id="headline-result" className="max-w-[24ch] text-display text-balance text-ink">
          Replay beats the judge by{' '}
          <span className="text-measure">
            <span className="sr-only">{formatPoints(gap.points)}</span>
            <motion.span
              ref={gapRef}
              aria-hidden="true"
              initial={reduced ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={springTransition('ticker', reduced)}
              className="inline-block num"
            >
              {formatPoints(gap.points)}
            </motion.span>
          </span>
        </h1>
        <p className="max-w-prose text-pretty text-ink-muted">
          Share of failures whose decisive step the method names correctly, on the same failures for
          both. The gap&rsquo;s 95% interval is{' '}
          <span className="num whitespace-nowrap text-ink">
            {formatPoints(gap.low)} to {formatPoints(gap.high)}
          </span>
          {gap.beatsZero ? ', which clears zero.' : ', which does not clear zero.'}
          {simulated ? ' These numbers are simulated — the API is serving fixtures.' : ''}
        </p>
      </header>

      <div className="flex flex-col gap-6">
        {bars.map((bar, index) => (
          <BarRow key={bar.id} bar={bar} index={index} />
        ))}
      </div>

      <div className="flex flex-col gap-1">
        <Axis />
        <span className="label-instrument">step accuracy (% of labelled failures)_</span>
      </div>
    </section>
  )
}
