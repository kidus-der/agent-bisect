import { ParentSize } from '@visx/responsive'
import { useReducedMotion } from 'motion/react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { roleColour } from '@/components/chart-theme/chartTheme'
import { Ring } from '@/components/charts/ring'
import { RingCenter } from '@/components/charts/ring-center'
import { RingChart } from '@/components/charts/ring-chart'
import { formatNumber } from '@/lib/format'
import { formatPercent } from '@/lib/stats'

import type { RateLimitStatus } from './api'

const RESIZE_DEBOUNCE_MS = 10
const RING_STROKE = 12
const RING_GAP = 5
const INNER_RADIUS = 46
const NO_MOTION = { duration: 0 } as const
const TIGHT_HEADROOM = 0.25

interface HeadroomRingProps {
  readonly rateLimit: RateLimitStatus
}

/** How much of the provider's per-minute limit is still free. */
export function HeadroomRing({ rateLimit }: HeadroomRingProps) {
  const reduced = useReducedMotion() === true
  const { limiter_rpm: limit, current_rpm: current, headroom_rpm: headroom } = rateLimit
  const headroomFraction = limit > 0 ? headroom / limit : 0
  const tight = headroomFraction <= TIGHT_HEADROOM
  const colour = tight ? roleColour('fail') : roleColour('measure')

  const data = [{ label: 'headroom', value: headroom, maxValue: limit || 1, color: colour }]

  return (
    <ChartFrame
      label="rate_limit"
      title="Headroom"
      description={`Ring of rate-limit headroom: ${formatNumber(current, { decimals: 1 })} of ${formatNumber(limit, { decimals: 0 })} requests per minute in use, leaving ${formatNumber(headroom, { decimals: 1 })} — ${formatPercent(headroomFraction, 0)} of the limiter free.`}
      heightClassName="h-44"
      legend={
        <span className="shrink-0 text-right num text-[12px] text-ink-muted">
          {formatNumber(current, { decimals: 1 })} rpm in use
          <br />
          <span className={tight ? 'text-fail' : ''}>
            {tight ? 'tight' : 'clear'} · limit {formatNumber(limit, { decimals: 0 })}
          </span>
        </span>
      }
    >
      <ParentSize debounceTime={RESIZE_DEBOUNCE_MS} className="flex items-center justify-center">
        {({ width, height }) => {
          const size = Math.floor(Math.min(width, height))
          if (size <= 0) return null
          return (
            <RingChart
              data={data}
              size={size}
              strokeWidth={RING_STROKE}
              ringGap={RING_GAP}
              baseInnerRadius={INNER_RADIUS}
              enterTransition={reduced ? NO_MOTION : undefined}
              enterStaggerScale={reduced ? 0 : undefined}
            >
              <Ring index={0} animate={!reduced} showGlow={false} />
              <RingCenter defaultLabel="rpm free" />
            </RingChart>
          )
        }}
      </ParentSize>
    </ChartFrame>
  )
}
