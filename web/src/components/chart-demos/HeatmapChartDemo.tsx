import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import {
  HeatmapCells,
  HeatmapChart,
  type HeatmapColumn,
  HeatmapInteractionBoundary,
  HeatmapInteractionProvider,
  HeatmapLegend,
  HeatmapTooltip,
  HeatmapXAxis,
  HeatmapYAxis,
} from '@/components/charts/heatmap'

import { BISECTIONS_PER_DAY } from './demoData'

const CELL_GAP = 2
const LEGEND_FONT_SIZE = 12

/** Bklit's column shape: one column per week, one bin per weekday, Sunday first. */
const CHART_DATA: HeatmapColumn[] = BISECTIONS_PER_DAY.map((week) => ({
  bin: week.week,
  bins: week.days.map((day, index) => ({ bin: index, count: day.count, date: day.date })),
}))

const ALL_DAYS = BISECTIONS_PER_DAY.flatMap((week) => week.days)
const TOTAL_BISECTIONS = ALL_DAYS.reduce((sum, day) => sum + day.count, 0)
const ACTIVE_DAYS = ALL_DAYS.filter((day) => day.count > 0).length

function formatBisections(count: number): string {
  return count === 1 ? '1 bisection' : `${count} bisections`
}

export function HeatmapChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <HeatmapInteractionProvider>
      <ChartFrame
        label="bisections_per_day"
        title="Daily bisections"
        description={`Calendar heatmap of bisections per day over ${BISECTIONS_PER_DAY.length} weeks from 3 May to 5 September 2026: ${TOTAL_BISECTIONS} bisections on ${ACTIVE_DAYS} active days, none at weekends, at most 4 in a day. Darker cells mean more bisections. Illustrative data.`}
        heightClassName="h-48"
        legend={
          <HeatmapLegend
            lessLabel="0"
            moreLabel="4+"
            fontSize={LEGEND_FONT_SIZE}
            className="w-auto shrink-0"
          />
        }
      >
        <HeatmapInteractionBoundary>
          <HeatmapChart
            data={CHART_DATA}
            layout="fill"
            gap={CELL_GAP}
            animate={!reduceMotion}
            animationDuration={reduceMotion ? 0 : undefined}
          >
            {/* Ghost-cell hiding compares bins with today's date; off keeps the render deterministic. */}
            <HeatmapCells hideGhostCells={false} />
            <HeatmapXAxis />
            <HeatmapYAxis />
            <HeatmapTooltip formatLabel={formatBisections} instant={reduceMotion} />
          </HeatmapChart>
        </HeatmapInteractionBoundary>
      </ChartFrame>
    </HeatmapInteractionProvider>
  )
}
