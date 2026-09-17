import { useReducedMotion } from 'motion/react'
import { useMemo } from 'react'

import { chartColours, roleColour } from '@/components/chart-theme/chartTheme'
import { Grid } from '@/components/charts/grid'
import { LiveLine } from '@/components/charts/live-line'
import { LiveLineChart, type LiveLinePoint } from '@/components/charts/live-line-chart'
import { LiveXAxis } from '@/components/charts/live-x-axis'
import { LiveYAxis } from '@/components/charts/live-y-axis'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import type { RoleName } from '@/design/tokens'
import { formatNumber } from '@/lib/format'

import type { CallsPoint } from './api'
import {
  type ModelSeries,
  buildModelSeries,
  seriesWindowSeconds,
  shortModelName,
} from './callsSeries'

const FALLBACK_WINDOW_SECONDS = 1800
const X_TICKS = 4
const INSTANT_LERP = 1
const MARGIN = { top: 18, right: 64, bottom: 28, left: 40 } as const
/** Cyan for the first model, violet for the second: two measurement channels, not a ranking. */
const SERIES_ROLES: readonly RoleName[] = ['measure', 'judge']

function formatRate(value: number): string {
  return value.toFixed(1)
}

interface ModelLineProps {
  readonly series: ModelSeries
  readonly index: number
  readonly windowSeconds: number
}

function ModelLine({ series, index, windowSeconds }: ModelLineProps) {
  const reduced = useReducedMotion() === true
  const colour = roleColour(SERIES_ROLES[index % SERIES_ROLES.length] ?? 'measure')
  // The chart's `data` prop is typed mutable, so it gets its own copy.
  const data: LiveLinePoint[] = useMemo(
    () => series.points.map((point) => ({ ...point })),
    [series.points],
  )
  const momentum = { up: colour, down: colour, flat: colour }

  return (
    <li className="flex min-w-0 flex-col gap-2 border-t border-line pt-4 first:border-t-0 first:pt-0">
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
      <div className="h-36 w-full min-w-0">
        <LiveLineChart
          data={data}
          value={series.latest}
          window={windowSeconds}
          numXTicks={X_TICKS}
          margin={MARGIN}
          paused={reduced}
          lerpSpeed={reduced ? INSTANT_LERP : undefined}
          style={{ height: '100%' }}
        >
          <Grid horizontal stroke={chartColours.grid} />
          <LiveLine
            dataKey="value"
            stroke={colour}
            momentumColors={momentum}
            pulse={!reduced}
            formatValue={formatRate}
          />
          <LiveXAxis numTicks={X_TICKS} />
          <LiveYAxis position="left" formatValue={formatRate} />
        </LiveLineChart>
      </div>
    </li>
  )
}

interface CallsPerModelProps {
  readonly rows: readonly CallsPoint[]
  readonly simulated: boolean
}

/** Focal element of the Live page: what each model is actually being asked to do. */
export function CallsPerModel({ rows, simulated }: CallsPerModelProps) {
  const series = useMemo(() => buildModelSeries(rows), [rows])
  const windowSeconds = seriesWindowSeconds(series, FALLBACK_WINDOW_SECONDS)
  const total = series.reduce((sum, entry) => sum + entry.latest, 0)

  return (
    <Panel variant="canvas" bodyClassName="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <InstrumentLabel>calls_per_minute</InstrumentLabel>
          <h2 className="text-h1 text-ink">What the models are doing</h2>
        </div>
        <div className="flex flex-col items-end">
          <span className="num text-display font-semibold text-ink">
            {formatNumber(total, { decimals: 1 })}
          </span>
          <span className="label-instrument">calls / min, all models</span>
        </div>
      </header>

      {series.length === 0 ? (
        <p className="py-8 text-ink-muted">No model has been called in this window.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {series.map((entry, index) => (
            <ModelLine
              key={entry.model}
              series={entry}
              index={index}
              windowSeconds={windowSeconds}
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
