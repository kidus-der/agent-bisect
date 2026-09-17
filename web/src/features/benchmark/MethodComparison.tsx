import { motion, useReducedMotion } from 'motion/react'
import { useId } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { STAGGER_SECONDS, springTransition } from '@/design/motion'
import { formatNumber } from '@/lib/format'
import { formatPercent, formatPoints } from '@/lib/stats'
import { cn } from '@/lib/utils'

import {
  AXIS_TICKS,
  MAX_RATE,
  accuracyAxisMax,
  rateFraction,
  ratePercent,
  rateSpanPercent,
} from './accuracyScale'
import type { MethodResult } from './api'
import { type MethodMeta, byMethodOrder, methodMeta } from './methods'
import { type PreregisteredBar, preregisteredBar } from './preregistration'

/**
 * One grid template, shared by the rows, the overlay marks and the axis, so the
 * pre-registered rule lands on the same x as the bars at every breakpoint.
 * Below `sm` the bar track is full width and the marks follow it.
 */
const ROW_GRID =
  'grid gap-x-4 grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,9rem)_minmax(0,1fr)_13.5rem] lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_13.5rem]'
/** The cell the scale lives in: whole width on mobile, the middle column above it. */
const TRACK_CELL = 'col-span-2 col-start-1 sm:col-span-1 sm:col-start-2'

/** The label is placed on whichever side of the rule has room. */
const RIGHT_EDGE_FRACTION = 0.7

const ROLE_FILL: Readonly<Record<string, string>> = {
  measure: 'var(--bx-measure)',
  judge: 'var(--bx-judge)',
  tape: 'var(--bx-tape)',
}

function roleFill(meta: MethodMeta): string {
  return ROLE_FILL[meta.role] ?? 'var(--bx-tape)'
}

interface MethodRowProps {
  readonly result: MethodResult
  readonly axisMax: number
  readonly index: number
  readonly focal: boolean
}

/** One method: what it does, the shape of its interval, and what it cost. */
function MethodRow({ result, axisMax, index, focal }: MethodRowProps) {
  const reduced = useReducedMotion() ?? false
  const meta = methodMeta(result.method)
  const fill = roleFill(meta)
  const { value, ci_low: low, ci_high: high } = result.accuracy
  const enter = {
    ...springTransition('settle', reduced),
    delay: reduced ? 0 : index * STAGGER_SECONDS.forest,
  }

  return (
    <motion.li
      initial={reduced ? undefined : { opacity: 0, y: 6 }}
      whileInView={reduced ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
      transition={enter}
      className={cn(ROW_GRID, 'items-center gap-y-2 border-b border-line py-3.5 last:border-b-0')}
    >
      <div className="col-span-2 flex min-w-0 flex-col gap-0.5 sm:col-span-1">
        <span className={cn('truncate text-ink', focal ? 'text-h2' : 'text-h3', 'font-semibold')}>
          {meta.label}
        </span>
        <span className="text-[12px] leading-4 text-pretty text-ink-muted">{meta.description}</span>
      </div>

      {/* The numbers to the right carry the reading; this is its shape. */}
      <div aria-hidden="true" className={cn(TRACK_CELL, 'relative min-w-0', focal ? 'h-9' : 'h-7')}>
        <motion.span
          initial={reduced ? undefined : { scaleX: 0 }}
          whileInView={reduced ? undefined : { scaleX: 1 }}
          viewport={{ once: true, amount: 0.35 }}
          transition={enter}
          style={{ width: ratePercent(value, axisMax), background: fill, originX: 0 }}
          className={cn(
            'absolute top-1/2 left-0 -translate-y-1/2 rounded-r-step',
            focal ? 'h-5' : 'h-3',
          )}
        />
        {meta.hatched ? (
          <span
            style={{ width: ratePercent(value, axisMax) }}
            className={cn(
              'absolute top-1/2 left-0 -translate-y-1/2 rounded-r-step hatch opacity-80',
              focal ? 'h-5' : 'h-3',
            )}
          />
        ) : null}
        <span
          style={{ left: ratePercent(low, axisMax), width: rateSpanPercent(low, high, axisMax) }}
          className="absolute top-1/2 h-px -translate-y-1/2 bg-ink"
        />
        {[low, high].map((bound) => (
          <span
            key={bound}
            style={{ left: ratePercent(bound, axisMax) }}
            className={cn(
              'absolute top-1/2 -ml-px w-px -translate-y-1/2 bg-ink',
              focal ? 'h-4' : 'h-3',
            )}
          />
        ))}
      </div>

      <div className="flex shrink-0 items-baseline justify-end gap-4 text-right sm:gap-6">
        <div className="flex flex-col items-end">
          <span className={cn('num text-ink', focal ? 'text-stat font-semibold' : 'text-h2')}>
            {formatPercent(value)}
          </span>
          <span className="num text-[12px] text-ink-muted">
            <span className="sr-only">95% bootstrap interval </span>[{formatPercent(low)},{' '}
            {formatPercent(high)}]
          </span>
        </div>
        <div className="hidden w-[5.5rem] flex-col items-end sm:flex">
          <span className="num text-small text-ink">
            {formatNumber(result.mean_cost_usd, { decimals: 2, prefix: '$' })}
          </span>
          <span className="num text-[12px] text-ink-muted">
            {formatNumber(Math.round(result.mean_calls), { decimals: 0 })}{' '}
            {Math.round(result.mean_calls) === 1 ? 'call' : 'calls'}
          </span>
        </div>
      </div>
    </motion.li>
  )
}

interface OverlayProps {
  readonly bar: PreregisteredBar | null
  readonly axisMax: number
}

/**
 * The two marks that belong to the scale rather than to any one method: the
 * pre-registered bar, and the hatched region past 100% that no method can reach.
 */
function ScaleOverlay({ bar, axisMax }: OverlayProps) {
  const nearRightEdge = bar !== null && rateFraction(bar.threshold, axisMax) > RIGHT_EDGE_FRACTION
  return (
    <div aria-hidden="true" className={cn(ROW_GRID, 'pointer-events-none absolute inset-0')}>
      <div className={cn(TRACK_CELL, 'relative')}>
        {axisMax > MAX_RATE ? (
          <div
            style={{ left: ratePercent(MAX_RATE, axisMax) }}
            className="absolute inset-y-0 right-0 border-l border-line-strong hatch opacity-50"
          />
        ) : null}
        {bar ? (
          <div
            style={{ left: ratePercent(bar.threshold, axisMax) }}
            className="absolute inset-y-0 w-px border-l border-dashed border-ink"
          >
            <span
              className={cn(
                'absolute top-0 rounded-step border border-line-strong bg-elevated px-1.5 py-0.5 label-instrument whitespace-nowrap text-ink',
                nearRightEdge ? 'right-2' : 'left-2',
              )}
            >
              pre-registered bar {formatPercent(bar.threshold)}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  )
}

interface AxisProps {
  readonly axisMax: number
}

function AccuracyAxis({ axisMax }: AxisProps) {
  return (
    <div aria-hidden="true" className={cn(ROW_GRID, 'mt-1')}>
      <div className={cn(TRACK_CELL, 'relative h-4')}>
        {AXIS_TICKS.map((tick) => (
          <span
            key={tick}
            style={{ left: ratePercent(tick, axisMax) }}
            className={cn(
              'absolute num text-[12px] text-ink-muted',
              tick === 0 ? '' : '-translate-x-1/2',
            )}
          >
            {formatPercent(tick, 0)}
          </span>
        ))}
      </div>
    </div>
  )
}

interface VerdictProps {
  readonly bar: PreregisteredBar
}

/** The headline the page exists to state, and whether the fixed bar was met. */
function PreregisteredVerdict({ bar }: VerdictProps) {
  const { cleared } = bar
  return (
    <div className="flex flex-wrap items-start gap-x-10 gap-y-5 rounded-card border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-col gap-1">
        <InstrumentLabel>bisect</InstrumentLabel>
        <span className="num text-display font-semibold text-ink">
          {formatPercent(bar.bisect.accuracy.value)}
        </span>
        <span className="num text-small text-ink-muted">
          95% CI [{formatPercent(bar.bisect.accuracy.ci_low)},{' '}
          {formatPercent(bar.bisect.accuracy.ci_high)}]
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <InstrumentLabel>vs best judge</InstrumentLabel>
        <span className="num text-stat text-ink">{formatPoints(bar.marginOverBestJudge)}</span>
        <span className="text-small text-ink-muted">
          over {methodMeta(bar.bestJudge.method).label.toLowerCase()}
        </span>
      </div>
      <div className="flex min-w-[16rem] flex-1 flex-col items-start gap-1.5">
        <InstrumentLabel>pre-registered bar</InstrumentLabel>
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-small font-medium',
            cleared
              ? 'border-pass/40 bg-pass-tint text-pass'
              : 'border-fail/40 bg-fail-tint text-fail',
          )}
        >
          <span aria-hidden="true">{cleared ? '✓' : '✕'}</span>
          {cleared ? 'met' : 'not met'} · {formatPercent(bar.threshold)}
        </span>
        <span className="max-w-prose text-[12px] leading-4 text-pretty text-ink-muted">
          {bar.unattainable
            ? 'Best judge + 15 points lands above 100%, so no method could clear it. The bar was fixed before measuring and is reported as it stands.'
            : 'Best judge + 15 points, fixed before measuring.'}
        </span>
      </div>
    </div>
  )
}

interface MethodComparisonProps {
  readonly methods: readonly MethodResult[]
}

/** Focal element of the Benchmark page: accuracy by method, with every interval. */
export function MethodComparison({ methods }: MethodComparisonProps) {
  const captionId = useId()
  const ordered = byMethodOrder(methods)
  const bar = preregisteredBar(methods)
  const axisMax = accuracyAxisMax(bar?.threshold)

  return (
    <Panel variant="canvas" bodyClassName="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <InstrumentLabel>step_accuracy</InstrumentLabel>
        <h2 className="text-h1 text-ink">Which method blames the right step</h2>
        <p id={captionId} className="max-w-prose text-pretty text-ink-muted">
          Share of labelled failures where the method named the planted step, with its 95% bootstrap
          interval. Mean cost is per diagnosis.
        </p>
      </header>

      {bar ? <PreregisteredVerdict bar={bar} /> : null}

      <div className="relative pt-7">
        <ScaleOverlay bar={bar} axisMax={axisMax} />
        <ul aria-describedby={captionId} className="relative m-0 list-none p-0">
          {ordered.map((result, index) => (
            <MethodRow
              key={result.method}
              result={result}
              axisMax={axisMax}
              index={index}
              focal={result.method === 'bisect'}
            />
          ))}
        </ul>
        <AccuracyAxis axisMax={axisMax} />
      </div>

      {axisMax > MAX_RATE ? (
        <p className="text-[12px] text-ink-muted">
          Hatched: above 100% accuracy, which no method can reach.
        </p>
      ) : null}
    </Panel>
  )
}
