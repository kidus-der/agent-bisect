import { ParentSize } from '@visx/responsive'
import { useReducedMotion } from 'motion/react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { roleColour } from '@/components/chart-theme/chartTheme'
import { Ring } from '@/components/charts/ring'
import { RingChart } from '@/components/charts/ring-chart'
import { springTransition } from '@/design/motion'
import { formatNumber } from '@/lib/format'
import { formatPercent } from '@/lib/stats'

import type { RateLimitStatus } from './api'

const RESIZE_DEBOUNCE_MS = 10
const RING_STROKE = 12
const RING_GAP = 5
const INNER_RADIUS = 46
const TIGHT_HEADROOM = 0.25
/**
 * Twelve o'clock, clockwise. The vendored default starts the arc at nine, which
 * puts a half-full ring's end at three and reads as three quarters spent.
 */
const RING_START_ANGLE = 0
const RING_END_ANGLE = Math.PI * 2

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

  // Filled = used, like every other gauge. The centre label stays the headroom,
  // which is the number an operator acts on.
  const data = [{ label: 'in use', value: current, maxValue: limit || 1, color: colour }]

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
            <div className="relative" style={{ width: size, height: size }}>
              <RingChart
                data={data}
                size={size}
                strokeWidth={RING_STROKE}
                ringGap={RING_GAP}
                baseInnerRadius={INNER_RADIUS}
                startAngle={RING_START_ANGLE}
                endAngle={RING_END_ANGLE}
                enterTransition={springTransition('drift', reduced)}
                enterStaggerScale={reduced ? 0 : undefined}
              >
                <Ring index={0} animate={!reduced} showGlow={false} />
              </RingChart>
              {/*
              The ring fills what is used, like every other gauge; the centre
              states what is left, which is the number an operator acts on.
              RingCenter's own render prop only fires while hovering, so the
              label is drawn here instead.
            */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
              >
                <span className="num text-stat text-ink">
                  {formatNumber(headroom, { decimals: 0 })}
                </span>
                <span className="label-instrument">rpm free</span>
              </span>
            </div>
          )
        }}
      </ParentSize>
    </ChartFrame>
  )
}
