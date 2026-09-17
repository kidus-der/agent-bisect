import { useCallback, useMemo, useState } from 'react'

import { roleColour } from '@/components/chart-theme/chartTheme'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import type { RoleName } from '@/design/tokens'
import { formatNumber } from '@/lib/format'

import type { CallsPoint } from './api'
import { type ModelSeries, buildModelSeries, sharedDomainMax, shortModelName } from './callsSeries'
import { TraceChart } from './TraceChart'

/** Cyan for the first model, violet for the second: two measurement channels, not a ranking. */
const SERIES_ROLES: readonly RoleName[] = ['measure', 'judge']

function formatRate(value: number): string {
  return value.toFixed(1)
}

interface ModelTraceProps {
  readonly series: ModelSeries
  readonly index: number
  readonly domainMax: number
  readonly cursorTime: number | null
  readonly onCursorTime: (time: number | null) => void
}

function ModelTrace({ series, index, domainMax, cursorTime, onCursorTime }: ModelTraceProps) {
  const colour = roleColour(SERIES_ROLES[index % SERIES_ROLES.length] ?? 'measure')
  return (
    <li className="flex min-w-0 flex-col gap-1.5 border-t border-line pt-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="num text-small font-medium text-ink">{shortModelName(series.model)}</span>
        <span className="flex items-baseline gap-3">
          <span className="num text-h2" style={{ color: colour }}>
            {formatRate(series.latest)}
          </span>
          <span className="num text-[12px] text-ink-muted">
            peak {formatRate(series.peak)} · calls/min
          </span>
        </span>
      </div>
      <div className="h-40 w-full min-w-0">
        <TraceChart
          points={series.points}
          colour={colour}
          domainMax={domainMax}
          formatValue={formatRate}
          cursorTime={cursorTime}
          onCursorTime={onCursorTime}
        />
      </div>
    </li>
  )
}

interface CallsPerModelProps {
  readonly rows: readonly CallsPoint[]
  readonly simulated: boolean
  /** The connection chip, hoisted into this panel's header: liveness belongs here. */
  readonly status?: React.ReactNode
}

/** Focal element of the Live page: what each model is actually being asked to do. */
export function CallsPerModel({ rows, simulated, status }: CallsPerModelProps) {
  const series = useMemo(() => buildModelSeries(rows), [rows])
  // One cursor for the whole panel: hovering either trace reads both at the same
  // instant, which is the comparison the panel exists to make.
  const [cursorTime, setCursorTime] = useState<number | null>(null)
  const handleCursorTime = useCallback((time: number | null) => setCursorTime(time), [])
  const domainMax = sharedDomainMax(series)
  const total = series.reduce((sum, entry) => sum + entry.latest, 0)

  return (
    <Panel variant="canvas" bodyClassName="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <InstrumentLabel>calls_per_minute</InstrumentLabel>
            {status}
          </div>
          <h2 className="text-h1 text-ink">What the models are doing</h2>
        </div>
        <div className="flex flex-col items-end">
          <span className="num text-display font-semibold text-ink">
            {formatNumber(total, { decimals: 1 })}
          </span>
          {/* The total is a sum across models, so it can and does exceed the
              per-trace axis; saying so stops the headline reading as off-scale. */}
          <span className="label-instrument">
            calls / min · sum of {series.length} {series.length === 1 ? 'model' : 'models'}
          </span>
          <span className="label-instrument">traces share 0–{domainMax}</span>
        </div>
      </header>

      {series.length === 0 ? (
        <p className="py-8 text-ink-muted">No model has been called in this window.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {series.map((entry, index) => (
            <ModelTrace
              key={entry.model}
              series={entry}
              index={index}
              domainMax={domainMax}
              cursorTime={cursorTime}
              onCursorTime={handleCursorTime}
            />
          ))}
        </ul>
      )}

      {simulated ? (
        <p className="text-[12px] text-ink-muted">
          Simulated traffic: this server is running on fixtures, so these rates are generated, not
          measured.
        </p>
      ) : null}
    </Panel>
  )
}
