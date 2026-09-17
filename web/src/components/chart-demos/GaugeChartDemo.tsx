import { ParentSize } from '@visx/responsive'
import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { Gauge } from '@/components/charts/gauge'

import { RATE_LIMIT_BUDGET } from './demoData'

/** The arc gauge is drawn for a 21:16 box; anything else letterboxes or overflows. */
const GAUGE_ASPECT = 21 / 16
const PERCENT = 100
const RESIZE_DEBOUNCE_MS = 10
const NO_MOTION = { duration: 0 } as const

const USED_PERCENT = (RATE_LIMIT_BUDGET.used / RATE_LIMIT_BUDGET.limit) * PERCENT
const REMAINING = RATE_LIMIT_BUDGET.limit - RATE_LIMIT_BUDGET.used

function fitGauge(
  width: number,
  height: number,
): { readonly width: number; readonly height: number } {
  const fittedWidth = Math.floor(Math.min(width, height * GAUGE_ASPECT))
  return { width: fittedWidth, height: Math.floor(fittedWidth / GAUGE_ASPECT) }
}

export function GaugeChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="rate_limit"
      title="Rate-limit budget this minute"
      description={`Gauge of provider calls used this minute: ${RATE_LIMIT_BUDGET.used} of ${RATE_LIMIT_BUDGET.limit} requests per minute, ${USED_PERCENT.toFixed(0)}% of the cap, leaving ${REMAINING} calls. Illustrative data.`}
    >
      <ParentSize debounceTime={RESIZE_DEBOUNCE_MS} className="flex items-center justify-center">
        {({ width, height }) => {
          const size = fitGauge(width, height)
          if (size.width <= 0 || size.height <= 0) return null
          return (
            <Gauge
              value={USED_PERCENT}
              centerValue={RATE_LIMIT_BUDGET.used}
              defaultLabel={`of ${RATE_LIMIT_BUDGET.limit} req/min`}
              totalNotches={RATE_LIMIT_BUDGET.limit}
              activeFill={chartColours.treated}
              inactiveFill={chartColours.grid}
              width={size.width}
              height={size.height}
              enterTransition={reduceMotion ? NO_MOTION : undefined}
              enterStaggerScale={reduceMotion ? 0 : undefined}
            />
          )
        }}
      </ParentSize>
    </ChartFrame>
  )
}
