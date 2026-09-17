import { curveMonotoneX } from '@visx/curve'
import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame, ChartLegend } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { Grid } from '@/components/charts/grid'
import { Line, LineChart } from '@/components/charts/line-chart'
import { ChartTooltip, TooltipContent } from '@/components/charts/tooltip'

import { RECALL_AT_M } from './demoData'

const ENTER_DURATION_MS = 1100
const MARGIN = { top: 16, right: 28, bottom: 32, left: 28 } as const
const MARKER_STYLE = { radius: 3, strokeWidth: 0, ringGap: 0 } as const

/**
 * LineChart only has a time x-scale, so the integer m is encoded as fake epoch
 * time, one second per step. The scale stays linear; the date axis, pill and
 * tooltip title are swapped for the ones below.
 */
const STEP_MS = 1000
/** Fraction of a step kept clear at each end, so the reveal clip does not cut the end markers. */
const X_PADDING_STEPS = 0.25
const FIRST_M = RECALL_AT_M[0]?.m ?? 1
const LAST_M = RECALL_AT_M.at(-1)?.m ?? FIRST_M
const X_START = FIRST_M - X_PADDING_STEPS
const X_SPAN = LAST_M - FIRST_M + 2 * X_PADDING_STEPS

const CHART_DATA = RECALL_AT_M.map((row) => ({ ...row, x: new Date(row.m * STEP_MS) }))
const X_DOMAIN: [Date, Date] = [new Date(X_START * STEP_MS), new Date((X_START + X_SPAN) * STEP_MS)]

const LEGEND = [
  { label: 'replay', colour: chartColours.treated },
  { label: 'llm judge', colour: chartColours.judge },
] as const

function tickLeft(m: number): string {
  const fraction = (m - X_START) / X_SPAN
  return `calc(${MARGIN.left}px + (100% - ${MARGIN.left + MARGIN.right}px) * ${fraction})`
}

function RecallAxis(): JSX.Element {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-1 h-4">
      {RECALL_AT_M.map((row) => (
        <span
          key={row.m}
          className="absolute -translate-x-1/2 num text-xs whitespace-nowrap"
          style={{ left: tickLeft(row.m), color: chartColours.label }}
        >
          m={row.m}
        </span>
      ))}
    </div>
  )
}

function RecallTooltip({ index }: { readonly index: number }): JSX.Element | null {
  const row = RECALL_AT_M[index]
  if (!row) return null
  return (
    <TooltipContent
      title={`top ${row.m} blamed step${row.m === 1 ? '' : 's'}`}
      rows={[
        { color: chartColours.treated, label: 'replay', value: `${row.replay}%` },
        { color: chartColours.judge, label: 'llm judge', value: `${row.judge}%` },
      ]}
    />
  )
}

export function LineChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="recall@m"
      title="Culprit in top m"
      description="Line chart of recall at m for m from 1 to 5. Counterfactual replay rises from 62% at m=1 to 94% at m=5; the LLM judge rises from 41% to 74%. Replay leads at every m. Illustrative data."
      legend={<ChartLegend entries={LEGEND} />}
    >
      <LineChart
        data={CHART_DATA}
        xDataKey="x"
        xDomain={X_DOMAIN}
        aspectRatio="auto"
        className="h-full"
        margin={MARGIN}
        animationDuration={reduceMotion ? 0 : ENTER_DURATION_MS}
        yDomainTween={!reduceMotion}
      >
        <Grid horizontal stroke={chartColours.grid} />
        <Line
          dataKey="replay"
          stroke={chartColours.treated}
          curve={curveMonotoneX}
          animate={!reduceMotion}
          fadeEdges={false}
          showMarkers
          markers={MARKER_STYLE}
        />
        <Line
          dataKey="judge"
          stroke={chartColours.judge}
          curve={curveMonotoneX}
          animate={!reduceMotion}
          fadeEdges={false}
          showMarkers
          markers={MARKER_STYLE}
        />
        <ChartTooltip
          showDatePill={false}
          content={({ index }) => <RecallTooltip index={index} />}
        />
      </LineChart>
      <RecallAxis />
    </ChartFrame>
  )
}
