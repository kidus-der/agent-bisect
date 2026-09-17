import { useReducedMotion } from 'motion/react'
import { type JSX, useEffect, useMemo, useState } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { Grid } from '@/components/charts/grid'
import { LiveLine } from '@/components/charts/live-line'
import { LiveLineChart, type LiveLinePoint } from '@/components/charts/live-line-chart'
import { LiveXAxis } from '@/components/charts/live-x-axis'
import { LiveYAxis } from '@/components/charts/live-y-axis'

import { CALLS_PER_SECOND_LOOP } from './demoData'

const WINDOW_SECONDS = 30
const TICK_MS = 1000
const MS_PER_SECOND = 1000
const X_TICKS = 4
/** A few seconds beyond the window, so the line never starts inside the plot. */
const MAX_POINTS = WINDOW_SECONDS + 4
const INSTANT_LERP = 1
const MARGIN = { top: 16, right: 56, bottom: 32, left: 36 } as const
/** One hue whichever way the series is heading: up/down is not a pass/fail signal here. */
const SINGLE_HUE = {
  up: chartColours.treated,
  down: chartColours.treated,
  flat: chartColours.treated,
} as const

interface LiveState {
  readonly points: readonly LiveLinePoint[]
  /** Index into the loop of the next value to emit. */
  readonly cursor: number
}

function loopValue(cursor: number): number {
  return CALLS_PER_SECOND_LOOP[cursor % CALLS_PER_SECOND_LOOP.length] ?? 0
}

function initialState(nowSeconds: number): LiveState {
  const count = CALLS_PER_SECOND_LOOP.length
  return {
    points: CALLS_PER_SECOND_LOOP.map((value, index) => ({
      time: nowSeconds - (count - 1 - index),
      value,
    })),
    cursor: count,
  }
}

function advance(state: LiveState, nowSeconds: number): LiveState {
  const next: LiveLinePoint = { time: nowSeconds, value: loopValue(state.cursor) }
  return {
    points: [...state.points.slice(-(MAX_POINTS - 1)), next],
    cursor: state.cursor + 1,
  }
}

function formatCalls(value: number): string {
  return String(Math.round(value))
}

export function LiveLineChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  const [state, setState] = useState<LiveState>(() => initialState(Date.now() / MS_PER_SECOND))

  useEffect(() => {
    if (reduceMotion) return undefined
    const timer = window.setInterval(() => {
      const nowSeconds = Date.now() / MS_PER_SECOND
      setState((previous) => advance(previous, nowSeconds))
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [reduceMotion])

  /** The chart's `data` prop is typed mutable, so it gets its own copy. */
  const chartData = useMemo(() => state.points.map((point) => ({ ...point })), [state.points])
  const latest = state.points.at(-1)?.value ?? 0

  return (
    <ChartFrame
      label="calls_per_sec"
      title="Provider calls per second"
      description={`Live line chart of provider calls per second over a ${WINDOW_SECONDS} second window, replaying an illustrative loop that ranges from 3 to 12 calls per second and adds one point each second. It renders as a static series when reduced motion is requested.`}
    >
      <LiveLineChart
        data={chartData}
        value={latest}
        window={WINDOW_SECONDS}
        numXTicks={X_TICKS}
        margin={MARGIN}
        paused={reduceMotion}
        lerpSpeed={reduceMotion ? INSTANT_LERP : undefined}
        style={{ height: '100%' }}
      >
        <Grid horizontal stroke={chartColours.grid} />
        <LiveLine
          dataKey="value"
          stroke={chartColours.treated}
          momentumColors={SINGLE_HUE}
          pulse={!reduceMotion}
          formatValue={formatCalls}
        />
        <LiveXAxis numTicks={X_TICKS} />
        <LiveYAxis position="left" allowDecimals={false} formatValue={formatCalls} />
      </LiveLineChart>
    </ChartFrame>
  )
}
