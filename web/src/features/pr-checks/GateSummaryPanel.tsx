import { Link } from '@tanstack/react-router'
import { motion, useReducedMotion } from 'motion/react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { STAGGER_SECONDS, springTransition } from '@/design/motion'
import { formatPoints } from '@/lib/stats'
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
}

/**
 * One check's change with its interval, on the axis every other check shares.
 * A forest plot, in the product's own idiom: point, whiskers, zero rule.
 */
function DeltaRow({ entry, bound, index }: DeltaRowProps) {
  const reduced = useReducedMotion() ?? false
  const colour = !entry.decisive ? 'bg-tape' : entry.delta < 0 ? 'bg-fail' : 'bg-pass'
  const low = entry.interval?.low ?? entry.delta
  const high = entry.interval?.high ?? entry.delta
  return (
    <motion.li
      initial={reduced ? undefined : { opacity: 0, x: -4 }}
      animate={reduced ? undefined : { opacity: 1, x: 0 }}
      transition={{
        ...springTransition('settle', reduced),
        delay: reduced ? 0 : index * STAGGER_SECONDS.forest,
      }}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 sm:grid-cols-[4rem_minmax(0,1fr)_5.5rem]"
    >
      <Link
        to="/pr-checks/$checkId"
        params={{ checkId: entry.checkId }}
        className="num text-[12px] text-measure underline-offset-2 hover:underline"
      >
        #{entry.prNumber}
      </Link>
      <span
        aria-hidden="true"
        className="relative order-last col-span-2 sm:order-none sm:col-span-1"
        style={{ height: ROW_HEIGHT }}
      >
        <span className="absolute inset-y-1 left-1/2 w-px bg-line-strong" />
        <span
          className={cn('absolute top-1/2 h-px -translate-y-1/2', colour)}
          style={{
            left: axisPercent(Math.min(low, high), bound),
            right: `calc(100% - ${axisPercent(Math.max(low, high), bound)})`,
          }}
        />
        {[low, high].map((bound_) => (
          <span
            key={bound_}
            className={cn('absolute top-1/2 -ml-px w-px -translate-y-1/2', colour)}
            style={{ left: axisPercent(bound_, bound), height: CAP_HALF * 2 }}
          />
        ))}
        <span
          className={cn(
            'absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-[1px]',
            colour,
          )}
          style={{ left: axisPercent(entry.delta, bound) }}
        />
      </span>
      <span
        className={cn('text-right num text-[12px]', entry.decisive ? 'text-ink' : 'text-ink-muted')}
      >
        {formatPoints(entry.delta, 0)}
      </span>
    </motion.li>
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
  const summary: GateSummary = buildGateSummary(checks)
  const bound = deltaAxisBound(summary)
  if (summary.deltas.length === 0) return null

  return (
    <Panel
      variant="elevated"
      bodyClassName="grid gap-6 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]"
    >
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
          zero. The rest are inside the noise of a {RUNS_PER_REF}-run suite, however their point
          estimate reads.
        </p>
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-center justify-between text-[12px] text-ink-muted">
          <span className="num">{formatPoints(-bound, 0)}</span>
          <span className="label-instrument">change per check · 95% CI</span>
          <span className="num">{formatPoints(bound, 0)}</span>
        </div>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {summary.deltas.map((entry, index) => (
            <DeltaRow key={entry.checkId} entry={entry} bound={bound} index={index} />
          ))}
        </ul>
      </div>
    </Panel>
  )
}
