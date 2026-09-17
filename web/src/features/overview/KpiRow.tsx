/**
 * The four numbers the project is accountable for. Deltas are absent because
 * `/api/overview` reports none — a KPI never invents its own trend.
 */
import { StatTicker } from '@/components/primitives/StatTicker'
import { cn } from '@/lib/utils'

import type { Kpis } from './api'

interface KpiRowProps {
  readonly kpis: Kpis
  readonly className?: string
}

interface KpiSpec {
  readonly id: string
  readonly label: string
  readonly value: number
  readonly caption: string
  readonly decimals?: number
  readonly prefix?: string
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
      id: 'cost',
      label: 'cost per diagnosis',
      value: kpis.cost_per_diagnosis_usd,
      caption: 'mean, USD',
      decimals: 2,
      prefix: '$',
    },
  ]
}

export function KpiRow({ kpis, className }: KpiRowProps) {
  return (
    // One rail, not four cards: a single 10px container divided by hairlines, so
    // the fold carries one object instead of four competing ones.
    <section
      aria-label="Key figures"
      className={cn(
        // Secondary to the headline panel: one fill step up, stronger hairline (as Panel's kpi variant).
        'grid grid-cols-2 overflow-hidden rounded-kpi border border-line-strong bg-elevated',
        'divide-x divide-y divide-line lg:grid-cols-1 lg:divide-x-0',
        className,
      )}
    >
      {kpiSpecs(kpis).map((spec) => (
        <div key={spec.id} className="flex min-h-21 flex-col justify-center px-4 py-3">
          <StatTicker
            label={spec.label}
            value={spec.value}
            caption={spec.caption}
            decimals={spec.decimals}
            prefix={spec.prefix}
          />
        </div>
      ))}
    </section>
  )
}
