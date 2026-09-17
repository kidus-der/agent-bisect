import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame, ChartLegend } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { Grid } from '@/components/charts/grid'
import { Scatter, ScatterChart } from '@/components/charts/scatter-chart'
import { ChartTooltip } from '@/components/charts/tooltip'
import { XAxis } from '@/components/charts/x-axis'

import { COST_BY_NIGHT } from './demoData'

const ENTER_DURATION_MS = 1100
const MARGIN = { top: 16, right: 24, bottom: 36, left: 24 } as const
const X_TICKS = 4
const POINT_RADIUS = 4
const NO_MOTION = { duration: 0 } as const

/** The chart's `data` prop is typed mutable, so it gets its own copy of the rows. */
const CHART_DATA = COST_BY_NIGHT.map((row) => ({ ...row }))

const LEGEND = [
  { label: 'replay', colour: chartColours.treated },
  { label: 'llm judge', colour: chartColours.judge },
] as const

function costRows(point: Record<string, unknown>) {
  const cents = (value: unknown): string => (typeof value === 'number' ? `${value}¢` : '–')
  return [
    { color: chartColours.treated, label: 'replay', value: cents(point.replay) },
    { color: chartColours.judge, label: 'llm judge', value: cents(point.judge) },
  ]
}

export function ScatterChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="cost_per_failure"
      title="Cost per failure"
      description="Scatter chart of mean cost per localised failure over 14 nightly benchmarks from 1 to 14 August 2026. Counterfactual replay falls from 21 to 15 cents; the LLM judge stays between 6 and 9 cents. Replay costs roughly twice as much per failure. Illustrative data."
      legend={<ChartLegend entries={LEGEND} />}
    >
      <ScatterChart
        data={CHART_DATA}
        aspectRatio="auto"
        className="h-full"
        margin={MARGIN}
        animationDuration={reduceMotion ? 0 : ENTER_DURATION_MS}
        enterTransition={reduceMotion ? NO_MOTION : undefined}
      >
        <Grid horizontal stroke={chartColours.grid} />
        {/* Explicit fills: the defaults fall back to the palette order, and the y-gradient to raw Tailwind red/emerald. */}
        <Scatter
          dataKey="replay"
          fill={chartColours.treated}
          radius={POINT_RADIUS}
          animate={!reduceMotion}
          enterBlur={reduceMotion ? 0 : undefined}
        />
        <Scatter
          dataKey="judge"
          fill={chartColours.judge}
          radius={POINT_RADIUS}
          animate={!reduceMotion}
          enterBlur={reduceMotion ? 0 : undefined}
        />
        <XAxis numTicks={X_TICKS} />
        <ChartTooltip rows={costRows} />
      </ScatterChart>
    </ChartFrame>
  )
}
