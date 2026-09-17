import { ParentSize } from '@visx/responsive'
import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame, ChartLegend } from '@/components/chart-theme/ChartFrame'
import { chartColours, roleColour } from '@/components/chart-theme/chartTheme'
import { RadarArea } from '@/components/charts/radar-area'
import { RadarAxis } from '@/components/charts/radar-axis'
import { RadarChart } from '@/components/charts/radar-chart'
import { RadarGrid } from '@/components/charts/radar-grid'
import { RadarLabels } from '@/components/charts/radar-labels'

import { AGREEMENT_METRICS, AGREEMENT_SERIES } from './demoData'

const RESIZE_DEBOUNCE_MS = 10
/** Room for the axis labels, which are centred on a point outside the polygon. */
const LABEL_MARGIN = 66
const LABEL_OFFSET = 30
const GRID_LEVELS = 5
const NO_MOTION = { duration: 0 } as const

const METRICS = AGREEMENT_METRICS.map((metric) => ({ ...metric }))
const CHART_DATA = AGREEMENT_SERIES.map((series) => ({
  label: series.label,
  color: roleColour(series.role),
  values: { ...series.values },
}))
const LEGEND = AGREEMENT_SERIES.map((series) => ({
  label: series.label,
  colour: roleColour(series.role),
}))

const SERIES_SUMMARY = AGREEMENT_SERIES.map((series) => {
  const scores = AGREEMENT_METRICS.map(
    (metric) => `${metric.label} ${series.values[metric.key] ?? 0}`,
  )
  return `${series.label}: ${scores.join(', ')}`
}).join('. ')

export function RadarChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="judge_vs_replay"
      title="Agreement with labels"
      description={`Radar chart scoring each method against human-labelled culprit steps on a 0 to 100 scale. ${SERIES_SUMMARY}. Replay leads on every axis except coverage. Illustrative data.`}
      heightClassName="h-72"
      legend={<ChartLegend entries={LEGEND} />}
    >
      <ParentSize debounceTime={RESIZE_DEBOUNCE_MS} className="flex items-center justify-center">
        {({ width, height }) => {
          const size = Math.floor(Math.min(width, height))
          if (size <= 0) return null
          return (
            <RadarChart
              data={CHART_DATA}
              metrics={METRICS}
              size={size}
              levels={GRID_LEVELS}
              margin={LABEL_MARGIN}
              animate={!reduceMotion}
              enterTransition={reduceMotion ? NO_MOTION : undefined}
            >
              <RadarGrid stroke={chartColours.grid} />
              <RadarAxis stroke={chartColours.grid} />
              <RadarLabels offset={LABEL_OFFSET} />
              {CHART_DATA.map((series, index) => (
                <RadarArea key={series.label} index={index} showGlow={false} />
              ))}
            </RadarChart>
          )
        }}
      </ParentSize>
    </ChartFrame>
  )
}
