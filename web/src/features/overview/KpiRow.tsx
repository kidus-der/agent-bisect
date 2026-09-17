/**
 * The four numbers the project is accountable for. Deltas are absent because
 * `/api/overview` reports none — a KPI never invents its own trend.
 */
import { Panel } from '@/components/primitives/Panel'
import { StatTicker } from '@/components/primitives/StatTicker'

import type { Kpis } from './api'

interface KpiRowProps {
  readonly kpis: Kpis
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

export function KpiRow({ kpis }: KpiRowProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {kpiSpecs(kpis).map((spec) => (
        <Panel key={spec.id} variant="kpi">
          <StatTicker
            label={spec.label}
            value={spec.value}
            caption={spec.caption}
            decimals={spec.decimals}
            prefix={spec.prefix}
          />
        </Panel>
      ))}
    </div>
  )
}
