/**
 * The four numbers the project is accountable for. Deltas are absent because
 * `/api/overview` reports none — a KPI never invents its own trend.
 */
import { useInView } from 'motion/react'
import { useRef } from 'react'

import { StatTicker } from '@/components/primitives/StatTicker'
import { COST_UNIT_LABEL, formatUsd } from '@/lib/cost'
import { cn } from '@/lib/utils'

import type { Kpis } from './api'

/** The four numbers read in sequence rather than all landing at once. */
const KPI_STAGGER_SECONDS = 0.09
/** Enough of the rail on screen to be worth counting up for. */
const IN_VIEW_AMOUNT = 0.4

interface KpiRowProps {
  readonly kpis: Kpis
  readonly className?: string
}

interface KpiSpec {
  readonly id: string
  readonly label: string
  /** Null when the server measured nothing for it — rendered as a dash. */
  readonly value: number | null
  readonly caption: string
  readonly decimals?: number
  readonly prefix?: string
}

function priceCaption(usd: number | null): string {
  const price = formatUsd(usd)
  return price === null ? `mean, ${COST_UNIT_LABEL}` : `mean, ${COST_UNIT_LABEL} · ${price}`
}

function kpiSpecs(kpis: Kpis): readonly KpiSpec[] {
  return [
    {
      id: 'runs',
      label: 'runs recorded',
      value: kpis.runs_recorded,
      caption: 'written to tape',
    },
    {
      id: 'diagnosed',
      label: 'failures diagnosed',
      value: kpis.failures_diagnosed,
      caption: 'a decisive step named',
    },
    {
      id: 'calls',
      label: 'calls spent',
      value: kpis.calls_spent,
      caption: 'model calls, all phases',
    },
    {
      // Calls are measured on every run; USD needs a price list that real mode
      // does not carry, so it rides in the caption when it exists at all.
      id: 'cost',
      label: 'cost per diagnosis',
      value: kpis.cost_per_diagnosis_calls,
      caption: priceCaption(kpis.cost_per_diagnosis_usd),
      decimals: 0,
    },
  ]
}

export function KpiRow({ kpis, className }: KpiRowProps) {
  const railRef = useRef<HTMLElement | null>(null)
  // Counting up on mount finished behind the page's own fade, so every number
  // was already final by the time it could be read. It waits to be looked at.
  const inView = useInView(railRef, { amount: IN_VIEW_AMOUNT, once: true })

  return (
    // One rail, not four cards: a single 10px container divided by hairlines, so
    // the fold carries one object instead of four competing ones.
    <section
      ref={railRef}
      aria-label="Key figures"
      className={cn(
        // Secondary to the headline panel: it recedes, with the stronger hairline (as Panel's kpi variant).
        'grid grid-cols-2 overflow-hidden rounded-kpi border border-line-strong bg-recessed',
        'divide-x divide-y divide-line lg:grid-cols-1 lg:divide-x-0',
        className,
      )}
    >
      {kpiSpecs(kpis).map((spec, index) => (
        <div key={spec.id} className="flex min-h-21 flex-col justify-center px-4 py-3">
          {spec.value === null ? (
            // Nothing measured: a dash, never a ticker counting up to zero.
            <div className="flex flex-col gap-1">
              <span className="label-instrument">{spec.label}</span>
              <span className="num text-stat text-ink-muted">—</span>
              <span className="label-instrument">{spec.caption}</span>
            </div>
          ) : (
            <StatTicker
              label={spec.label}
              value={spec.value}
              caption={spec.caption}
              decimals={spec.decimals}
              prefix={spec.prefix}
              delaySeconds={index * KPI_STAGGER_SECONDS}
              play={inView}
            />
          )}
        </div>
      ))}
    </section>
  )
}
