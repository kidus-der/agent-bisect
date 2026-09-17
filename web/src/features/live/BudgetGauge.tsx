import { ParentSize } from '@visx/responsive'
import { useReducedMotion } from 'motion/react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours, roleColour } from '@/components/chart-theme/chartTheme'
import { Gauge } from '@/components/charts/gauge'
import { NotMeasuredState } from '@/components/primitives/NotMeasuredState'
import { formatNumber } from '@/lib/format'
import { formatPercent } from '@/lib/stats'

import type { BudgetStatus } from './api'

/** The arc gauge is drawn for a 21:16 box; anything else letterboxes or overflows. */
const GAUGE_ASPECT = 21 / 16
const RESIZE_DEBOUNCE_MS = 10
const NO_MOTION = { duration: 0 } as const
/** Notches are drawn one per unit, so a 12 000-call cap is rescaled to a readable count. */
const NOTCH_COUNT = 60
const WARN_FRACTION = 0.8

function fitGauge(width: number, height: number) {
  const fittedWidth = Math.floor(Math.min(width, height * GAUGE_ASPECT))
  return { width: fittedWidth, height: Math.floor(fittedWidth / GAUGE_ASPECT) }
}

interface BudgetGaugeProps {
  readonly budget: BudgetStatus
}

/** Calls spent against the configured daily cap. No cap configured is said, not guessed. */
export function BudgetGauge({ budget }: BudgetGaugeProps) {
  const reduced = useReducedMotion() === true
  const { used, cap } = budget

  if (cap === null) {
    return (
      <div className="rounded-chart border border-line bg-surface p-4">
        <NotMeasuredState
          label="budget"
          title="No call cap is configured"
          reason={`${formatNumber(used, { decimals: 0 })} calls spent, against no configured cap.`}
        />
      </div>
    )
  }

  const fraction = cap > 0 ? used / cap : 0
  const remaining = Math.max(0, cap - used)
  const hot = fraction >= WARN_FRACTION
  const activeFill = hot ? roleColour('fail') : roleColour('measure')

  return (
    <ChartFrame
      label="daily_budget"
      title="Call budget"
      description={`Gauge of the daily call budget: ${formatNumber(used, { decimals: 0 })} of ${formatNumber(cap, { decimals: 0 })} calls spent, ${formatPercent(fraction, 0)} of the cap, leaving ${formatNumber(remaining, { decimals: 0 })}.`}
      heightClassName="h-44"
      legend={
        <span className="shrink-0 text-right num text-[12px] text-ink-muted">
          {formatNumber(remaining, { decimals: 0 })} left
          <br />
          <span className={hot ? 'text-fail' : ''}>{formatPercent(fraction, 0)} spent</span>
        </span>
      }
    >
      <ParentSize debounceTime={RESIZE_DEBOUNCE_MS} className="flex items-center justify-center">
        {({ width, height }) => {
          const size = fitGauge(width, height)
          if (size.width <= 0 || size.height <= 0) return null
          return (
            <Gauge
              value={fraction * 100}
              centerValue={used}
              defaultLabel={`of ${formatNumber(cap, { decimals: 0 })} calls`}
              totalNotches={NOTCH_COUNT}
              activeFill={activeFill}
              inactiveFill={chartColours.grid}
              width={size.width}
              height={size.height}
              enterTransition={reduced ? NO_MOTION : undefined}
              enterStaggerScale={reduced ? 0 : undefined}
            />
          )
        }}
      </ParentSize>
    </ChartFrame>
  )
}
