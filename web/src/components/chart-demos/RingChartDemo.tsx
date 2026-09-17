import { ParentSize } from '@visx/responsive'
import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame, ChartLegend } from '@/components/chart-theme/ChartFrame'
import { roleColour } from '@/components/chart-theme/chartTheme'
import { Ring } from '@/components/charts/ring'
import { RingCenter } from '@/components/charts/ring-center'
import { RingChart } from '@/components/charts/ring-chart'

import { DAILY_SPEND } from './demoData'

const RESIZE_DEBOUNCE_MS = 10
const RING_STROKE = 10
const RING_GAP = 5
const INNER_RADIUS = 52
const NO_MOTION = { duration: 0 } as const
const USD_FORMAT = { style: 'currency', currency: 'USD', maximumFractionDigits: 2 } as const

/** Bklit's ring shape; `value / maxValue` is the arc fraction. */
const CHART_DATA = DAILY_SPEND.map((ring) => ({
  label: ring.label,
  value: ring.spentUsd,
  maxValue: ring.capUsd,
  color: roleColour(ring.role),
}))

const LEGEND = DAILY_SPEND.map((ring) => ({ label: ring.label, colour: roleColour(ring.role) }))

const TOTAL_SPENT = DAILY_SPEND.reduce((sum, ring) => sum + ring.spentUsd, 0)
const TOTAL_CAP = DAILY_SPEND.reduce((sum, ring) => sum + ring.capUsd, 0)
const SPEND_SUMMARY = DAILY_SPEND.map(
  (ring) => `${ring.label} $${ring.spentUsd.toFixed(2)} of $${ring.capUsd.toFixed(2)}`,
).join('; ')

export function RingChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="headroom"
      title="Daily spend"
      description={`Ring chart of today's spend against each stage's daily cap: ${SPEND_SUMMARY}. In total $${TOTAL_SPENT.toFixed(2)} of $${TOTAL_CAP.toFixed(2)} is spent, leaving $${(TOTAL_CAP - TOTAL_SPENT).toFixed(2)} of headroom. Illustrative data.`}
      legend={<ChartLegend entries={LEGEND} />}
    >
      <ParentSize debounceTime={RESIZE_DEBOUNCE_MS} className="flex items-center justify-center">
        {({ width, height }) => {
          const size = Math.floor(Math.min(width, height))
          if (size <= 0) return null
          return (
            <RingChart
              data={CHART_DATA}
              size={size}
              strokeWidth={RING_STROKE}
              ringGap={RING_GAP}
              baseInnerRadius={INNER_RADIUS}
              enterTransition={reduceMotion ? NO_MOTION : undefined}
              enterStaggerScale={reduceMotion ? 0 : undefined}
            >
              {CHART_DATA.map((ring, index) => (
                <Ring key={ring.label} index={index} animate={!reduceMotion} showGlow={false} />
              ))}
              <RingCenter defaultLabel="spent today" formatOptions={USD_FORMAT} />
            </RingChart>
          )
        }}
      </ParentSize>
    </ChartFrame>
  )
}
