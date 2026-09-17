/**
 * The marks that make a run row readable at a glance: a step sparkline, a blame
 * stripe with untested steps hatched, an outcome glyph, and the decisive step
 * with its effect. Anything the API reports as null renders as an em dash —
 * never as a zero.
 */
import { BlameBadge } from '@/components/primitives/BlameBadge'
import { HeatStripe, type HeatStep } from '@/components/primitives/HeatStripe'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { StepSparkline } from '@/components/primitives/StepSparkline'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

import type { BlameCell, RunSummary, SparkPoint } from './api'

export const NOT_MEASURED = '—'

/** Keeps a 60-step stripe the same width as a 12-step one. */
const STRIPE_TARGET_PX = 132
const STRIPE_MIN_CELL_PX = 2
const STRIPE_MAX_CELL_PX = 12
const STRIPE_GAP_PX = 2

interface SparkSeries {
  readonly values: readonly number[]
  readonly label: string
}

/**
 * Tokens per step where every step has them, else latency. A series with any
 * gap is not drawn: a sparkline with an invented zero would read as a real dip.
 */
export function sparkSeries(points: readonly SparkPoint[]): SparkSeries | null {
  if (points.length === 0) return null
  const tokens = points.map((point) => point.tokens)
  if (tokens.every((value): value is number => value !== null)) {
    return { values: tokens, label: 'tokens per step' }
  }
  const latency = points.map((point) => point.latency_ms)
  if (latency.every((value): value is number => value !== null)) {
    return { values: latency, label: 'latency per step, ms' }
  }
  return null
}

/** Kept for callers that still size by cell; the stripe itself prefers a track. */
export function stripeCellWidth(steps: number, targetPx = STRIPE_TARGET_PX): number {
  if (steps <= 0) return STRIPE_MAX_CELL_PX
  const fitted = Math.floor(targetPx / steps) - STRIPE_GAP_PX
  return Math.min(STRIPE_MAX_CELL_PX, Math.max(STRIPE_MIN_CELL_PX, fitted))
}

export function toHeatSteps(stripe: readonly BlameCell[]): readonly HeatStep[] {
  return stripe.map((cell) => ({ step: cell.step_idx, effect: cell.tested ? cell.effect : null }))
}

/** The measured effect at the run's decisive step, or null if it was never tested. */
export function decisiveEffect(run: RunSummary): number | null {
  if (run.decisive_step === null) return null
  const cell = run.blame_stripe.find((entry) => entry.step_idx === run.decisive_step)
  return cell?.tested ? cell.effect : null
}

export function NotMeasured() {
  return (
    <span className="text-ink-muted">
      <span aria-hidden="true">{NOT_MEASURED}</span>
      <span className="sr-only">not measured</span>
    </span>
  )
}

export function RunSparkline({ run }: { readonly run: RunSummary }) {
  const series = sparkSeries(run.sparkline)
  if (!series) return <NotMeasured />
  return (
    <StepSparkline
      values={series.values}
      label={series.label}
      markIndex={run.decisive_step === null ? undefined : run.decisive_step - 1}
    />
  )
}

interface RunBlameStripeProps {
  readonly run: RunSummary
  /** Width the stripe fills, so step position stays comparable down a column. */
  readonly targetPx?: number
}

export function RunBlameStripe({ run, targetPx }: RunBlameStripeProps) {
  if (run.blame_stripe.length === 0) return <NotMeasured />
  return (
    <HeatStripe
      steps={toHeatSteps(run.blame_stripe)}
      blamedStep={run.decisive_step ?? undefined}
      trackWidth={targetPx ?? STRIPE_TARGET_PX}
      showBlameCaption={false}
    />
  )
}

/** Outcome is never colour alone, and a recording run is never called a failure. */
export function RunOutcome({ run }: { readonly run: RunSummary }) {
  if (run.status === 'recording') {
    return (
      <span className="inline-flex h-6 items-center gap-1.5 rounded-pill border border-line-strong bg-elevated px-2 text-small font-medium whitespace-nowrap text-ink-muted">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-measure" />
        Recording
      </span>
    )
  }
  if (run.outcome === null) return <NotMeasured />
  return <PassFailPill outcome={run.outcome} size="sm" />
}

export function RunBlame({ run }: { readonly run: RunSummary }) {
  const effect = decisiveEffect(run)
  if (run.decisive_step === null || effect === null) return <NotMeasured />
  return <BlameBadge step={run.decisive_step} effect={effect} size="sm" />
}

interface NumericProps {
  readonly value: number | null
  readonly decimals?: number
  readonly prefix?: string
  readonly className?: string
}

export function RunNumber({ value, decimals = 0, prefix, className }: NumericProps) {
  if (value === null) return <NotMeasured />
  return <span className={cn('num', className)}>{formatNumber(value, { decimals, prefix })}</span>
}
