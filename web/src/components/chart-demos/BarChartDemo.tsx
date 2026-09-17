import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { Bar } from '@/components/charts/bar'
import { BarChart } from '@/components/charts/bar-chart'
import { BarXAxis } from '@/components/charts/bar-x-axis'
import { Grid } from '@/components/charts/grid'
import { ChartTooltip } from '@/components/charts/tooltip'

import { COST_PER_RUN_BINS } from './demoData'

const ENTER_DURATION_MS = 1100
const MARGIN = { top: 16, right: 16, bottom: 36, left: 16 } as const
const BAR_CORNER_RADIUS = 3

/** The chart's `data` prop is typed mutable, so it gets its own copy of the rows. */
const CHART_DATA = COST_PER_RUN_BINS.map((row) => ({ ...row }))

function runRows(point: Record<string, unknown>) {
  return [
    {
      color: chartColours.treated,
      label: 'runs',
      value: typeof point.runs === 'number' ? point.runs : 0,
    },
  ]
}

export function BarChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="cost_per_run"
      title="Cost to bisect one run"
      description="Histogram of 116 bisected runs by cost in 5 cent bins. The mode is the 10 to 15 cent bin with 34 runs; 80 runs cost between 5 and 20 cents and only 2 cost 35 cents or more. Illustrative data."
    >
      <BarChart
        data={CHART_DATA}
        xDataKey="bin"
        aspectRatio="auto"
        className="h-full"
        margin={MARGIN}
        barGap={0.15}
        animationDuration={reduceMotion ? 0 : ENTER_DURATION_MS}
      >
        <Grid horizontal stroke={chartColours.grid} />
        <Bar
          dataKey="runs"
          fill={chartColours.treated}
          lineCap={BAR_CORNER_RADIUS}
          animate={!reduceMotion}
        />
        <BarXAxis showAllLabels />
        <ChartTooltip showCrosshair={false} showDots={false} rows={runRows} />
      </BarChart>
    </ChartFrame>
  )
}
