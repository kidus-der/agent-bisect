import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { FunnelChart } from '@/components/charts/funnel-chart'

import { BISECT_FUNNEL } from './demoData'

const HALO_LAYERS = 2
const SEGMENT_GAP = 4
const PERCENT = 100
const NO_MOTION = { duration: 0 } as const
/** Replaces the funnel's built-in aspect ratio so it fills the frame instead. */
const FILL_FRAME = { aspectRatio: 'auto', height: '100%' } as const

/** The chart's `data` prop is typed mutable, so it gets its own copy of the stages. */
const CHART_DATA = BISECT_FUNNEL.map((stage) => ({ ...stage }))

const integerFormat = new Intl.NumberFormat('en-US')
const FIRST_STAGE_VALUE = BISECT_FUNNEL[0]?.value ?? 0
const STAGE_SUMMARY = BISECT_FUNNEL.map((stage) => {
  const share = FIRST_STAGE_VALUE > 0 ? (stage.value / FIRST_STAGE_VALUE) * PERCENT : 0
  return `${stage.label} ${integerFormat.format(stage.value)} (${share.toFixed(0)}%)`
}).join(', ')

function formatCount(value: number): string {
  return integerFormat.format(value)
}

function formatShare(percentage: number): string {
  return `${percentage.toFixed(0)}%`
}

export function FunnelChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="bisect_funnel"
      title="From recorded run to confirmed blame"
      description={`Funnel chart of how many runs reach each stage, with the share of recorded runs: ${STAGE_SUMMARY}. Illustrative data.`}
      heightClassName="h-80"
    >
      {/* Side padding: the nowrap stage labels may spill a few pixels past their 16% column. */}
      <div className="h-full px-3">
        <FunnelChart
          data={CHART_DATA}
          orientation="vertical"
          color={chartColours.treated}
          layers={HALO_LAYERS}
          gap={SEGMENT_GAP}
          edges="straight"
          style={FILL_FRAME}
          formatValue={formatCount}
          formatPercentage={formatShare}
          staggerDelay={reduceMotion ? 0 : undefined}
          enterTransition={reduceMotion ? NO_MOTION : undefined}
        />
      </div>
    </ChartFrame>
  )
}
