import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame, ChartLegend } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { Area, AreaChart } from '@/components/charts/area-chart'
import { Grid } from '@/components/charts/grid'
import { ChartTooltip } from '@/components/charts/tooltip'
import { XAxis } from '@/components/charts/x-axis'

import { PASS_RATE_BY_NIGHT } from './demoData'

const ENTER_DURATION_MS = 1100
const MARGIN = { top: 16, right: 24, bottom: 36, left: 24 } as const
const X_TICKS = 4

/** The chart's `data` prop is typed mutable, so it gets its own copy of the rows. */
const CHART_DATA = PASS_RATE_BY_NIGHT.map((row) => ({ ...row }))

const LEGEND = [
  { label: 'treated', colour: chartColours.treated },
  { label: 'control', colour: chartColours.control },
] as const

function passRateRows(point: Record<string, unknown>) {
  const percent = (value: unknown): string => (typeof value === 'number' ? `${value}%` : '–')
  return [
    { color: chartColours.treated, label: 'treated', value: percent(point.treated) },
    { color: chartColours.control, label: 'control', value: percent(point.control) },
  ]
}

export function AreaChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="pass_rate"
      title="Treated vs control"
      description="Area chart of nightly pass rate over 14 nights from 1 to 14 August 2026. Treated re-runs climb from 58% to 81%; control re-runs stay between 30% and 37%. Illustrative data."
      legend={<ChartLegend entries={LEGEND} />}
    >
      <AreaChart
        data={CHART_DATA}
        aspectRatio="auto"
        className="h-full"
        margin={MARGIN}
        animationDuration={reduceMotion ? 0 : ENTER_DURATION_MS}
        yDomainTween={!reduceMotion}
      >
        <Grid horizontal stroke={chartColours.grid} />
        <Area
          dataKey="control"
          fill={chartColours.control}
          fillOpacity={0.2}
          animate={!reduceMotion}
        />
        <Area
          dataKey="treated"
          fill={chartColours.treated}
          fillOpacity={0.3}
          animate={!reduceMotion}
        />
        <XAxis numTicks={X_TICKS} />
        <ChartTooltip rows={passRateRows} />
      </AreaChart>
    </ChartFrame>
  )
}
