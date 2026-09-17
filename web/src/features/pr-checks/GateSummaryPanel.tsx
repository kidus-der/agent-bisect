import { Link } from '@tanstack/react-router'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { useRef } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { forestDotMotion, forestRowDelay, forestWhiskerMotion } from '@/design/forestEntrance'
import { formatPoints } from '@/lib/stats'

import { checkBadge } from './checkRef'
import { cn } from '@/lib/utils'

import type { PrCheckSummary } from './api'
import {
  type CheckDelta,
  type GateSummary,
  RUNS_PER_REF,
  buildGateSummary,
  deltaAxisBound,
} from './gateSummary'

const PERCENT = 100
const CAP_HALF = 4
const ROW_HEIGHT = 22

/** Fraction of the symmetric axis, with zero at the centre. */
function axisPercent(value: number, bound: number): string {
  const clamped = Math.min(bound, Math.max(-bound, value))
  return `${(0.5 + clamped / (2 * bound)) * PERCENT}%`
}

interface DeltaRowProps {
  readonly entry: CheckDelta
  readonly bound: number
  readonly index: number
  readonly total: number
  /** Held until the panel is actually looked at, so the entrance is not missed. */
  readonly entered: boolean
}

/**
 * One check's change with its interval, on the axis every other check shares.
 * A forest plot, in the product's own idiom: point, whiskers, zero rule.
 */
function DeltaRow({ entry, bound, index, total, entered }: DeltaRowProps) {
  const reduced = useReducedMotion() ?? false
  const colour = !entry.decisive ? 'bg-tape' : entry.delta < 0 ? 'bg-fail' : 'bg-pass'
  const low = entry.interval?.low ?? entry.delta
  const high = entry.interval?.high ?? entry.delta
  // The flagged checks arrive after the clean ones: "found", not "one of many".
  const delay = forestRowDelay({ index, total, deferred: entry.isRegression, reduced })
  const whisker = forestWhiskerMotion(delay, reduced)
  const dot = forestDotMotion(delay, reduced)
  const estimateLeft = axisPercent(entry.delta, bound)
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 sm:grid-cols-[3.5rem_minmax(0,1fr)_5rem]">
      <Link
        to="/pr-checks/$checkId"
        params={{ checkId: entry.checkId }}
        className="num text-[12px] text-measure underline-offset-2 hover:underline"
      >
        {checkBadge(entry.prNumber) ?? entry.title}
      </Link>
      <span
        aria-hidden="true"
        className="relative order-last col-span-2 sm:order-none sm:col-span-1"
        style={{ height: ROW_HEIGHT }}
      >
        <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
        {/* The interval draws outward from the estimate (§7.3). */}
        <motion.span
          className="absolute inset-0"
          style={{ transformOrigin: `${estimateLeft} 50%` }}
          initial={whisker.initial}
          animate={entered || reduced ? whisker.animate : whisker.initial || undefined}
          transition={whisker.transition}
        >
          <span
            className={cn('absolute top-1/2 h-px -translate-y-1/2', colour)}
            style={{
              left: axisPercent(Math.min(low, high), bound),
              right: `calc(100% - ${axisPercent(Math.max(low, high), bound)})`,
            }}
          />
          {[low, high].map((edge) => (
            <span
              key={edge}
              className={cn('absolute top-1/2 -ml-px w-px -translate-y-1/2', colour)}
              style={{ left: axisPercent(edge, bound), height: CAP_HALF * 2 }}
            />
          ))}
        </motion.span>
        {/* Then the estimate pops in, outlined so it reads against its own interval. */}
        <motion.span
          className={cn(
            'absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-[1px] ring-1 ring-ground',
            colour,
          )}
          style={{ left: estimateLeft }}
          initial={dot.initial}
          animate={entered || reduced ? dot.animate : dot.initial || undefined}
          transition={dot.transition}
        />
      </span>
      <span
        className={cn('text-right num text-[12px]', entry.decisive ? 'text-ink' : 'text-ink-muted')}
      >
        {formatPoints(entry.delta, 0)}
      </span>
    </li>
  )
}

function Stat({
  label,
  value,
  caption,
  tone,
}: {
  readonly label: string
  readonly value: string
  readonly caption?: string
  readonly tone?: 'fail' | 'ink'
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <InstrumentLabel>{label}</InstrumentLabel>
      <span className={cn('num text-stat', tone === 'fail' ? 'text-fail' : 'text-ink')}>
        {value}
      </span>
      {caption ? <span className="text-[12px] text-ink-muted">{caption}</span> : null}
    </div>
  )
}

interface GateSummaryPanelProps {
  readonly checks: readonly PrCheckSummary[]
}

/**
 * What the gate has found so far, from the list payload the page already holds.
 * Every number here is derived; nothing is fetched or assumed.
 */
export function GateSummaryPanel({ checks }: GateSummaryPanelProps) {
  const plotRef = useRef<HTMLDivElement>(null)
  const entered = useInView(plotRef, { once: true, amount: 0.4 })
  const summary: GateSummary = buildGateSummary(checks)
  const bound = deltaAxisBound(summary)
  if (summary.deltas.length === 0) return null

  return (
    <Panel variant="card" bodyClassName="grid gap-6 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <InstrumentLabel>gate_history</InstrumentLabel>
          <h3 className="text-h3 text-ink">What the gate has caught</h3>
        </div>
        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <Stat
            label="flagged"
            value={String(summary.regressions)}
            caption={`of ${summary.deltas.length} checks`}
            tone="fail"
          />
          <Stat
            label="median change"
            value={formatPoints(summary.medianDelta, 0)}
            caption="across every check"
          />
        </div>
        <p className="max-w-prose text-[12px] text-pretty text-ink-muted">
          {summary.decisiveCount} of {summary.deltas.length} changes have an interval that excludes
          zero. The rest are inside the noise of a {RUNS_PER_REF}-run suite, whatever their point
          estimate reads.
        </p>
      </div>

      <div ref={plotRef} className="flex min-w-0 flex-col gap-2">
        <span className="label-instrument">change per check · 95% CI</span>
        {/* The axis, with zero labelled: a forest plot is read against zero. */}
        <div
          aria-hidden="true"
          className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 sm:grid-cols-[3.5rem_minmax(0,1fr)_5rem]"
        >
          <span className="hidden sm:block" />
          <span className="relative col-span-2 h-4 sm:col-span-1">
            <span className="absolute left-0 num text-[12px] text-ink-muted">
              {formatPoints(-bound, 0)}
            </span>
            <span className="absolute left-1/2 -translate-x-1/2 num text-[12px] text-ink-muted">
              0
            </span>
            <span className="absolute right-0 num text-[12px] text-ink-muted">
              {formatPoints(bound, 0)}
            </span>
          </span>
        </div>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {summary.deltas.map((entry, index) => (
            <DeltaRow
              key={entry.checkId}
              entry={entry}
              bound={bound}
              index={index}
              total={summary.deltas.length}
              entered={entered}
            />
          ))}
        </ul>
      </div>
    </Panel>
  )
}
