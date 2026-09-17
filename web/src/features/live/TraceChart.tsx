import { curveMonotoneX } from '@visx/curve'
import { GridRows } from '@visx/grid'
import { Group } from '@visx/group'
import { LinearGradient } from '@visx/gradient'
import { ParentSize } from '@visx/responsive'
import { scaleLinear, scaleTime } from '@visx/scale'
import { Area, LinePath } from '@visx/shape'
import { motion, useReducedMotion } from 'motion/react'
import { useId } from 'react'

import { springTransition } from '@/design/motion'

import type { SeriesPoint } from './callsSeries'

const MARGIN = { top: 10, right: 58, bottom: 22, left: 40 } as const
const Y_TICKS = 3
/** Room each clock label needs before its neighbour starts touching it. */
const X_TICK_PITCH_PX = 88
const MAX_X_TICKS = 5
const MIN_X_TICKS = 2
const LINE_WIDTH = 2
const AREA_OPACITY = 0.18
const TIP_RADIUS = 3.5
const PULSE_SECONDS = 1.8
const BADGE_HEIGHT = 20
const BADGE_CHAR_WIDTH = 7.2
const BADGE_PADDING = 10
const MS_PER_SECOND = 1000

/** Hours and minutes only: the window is tens of minutes, and seconds collide. */
function formatClock(date: Date): string {
  return date.toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit' })
}

function xTickCount(innerWidth: number): number {
  return Math.max(MIN_X_TICKS, Math.min(MAX_X_TICKS, Math.floor(innerWidth / X_TICK_PITCH_PX)))
}

interface PlotProps {
  readonly width: number
  readonly height: number
  readonly points: readonly SeriesPoint[]
  readonly colour: string
  readonly domainMax: number
  readonly formatValue: (value: number) => string
  readonly gradientId: string
}

function Plot({ width, height, points, colour, domainMax, formatValue, gradientId }: PlotProps) {
  const reduced = useReducedMotion() ?? false
  const innerWidth = Math.max(0, width - MARGIN.left - MARGIN.right)
  const innerHeight = Math.max(0, height - MARGIN.top - MARGIN.bottom)
  const first = points[0]
  const last = points.at(-1)
  if (innerWidth <= 0 || innerHeight <= 0 || !first || !last) return null

  const x = scaleTime<number>({
    domain: [new Date(first.time * MS_PER_SECOND), new Date(last.time * MS_PER_SECOND)],
    range: [0, innerWidth],
  })
  // Shared across every trace on the page, so two traces can be compared by eye.
  const y = scaleLinear<number>({ domain: [0, domainMax], range: [innerHeight, 0] })

  const px = (point: SeriesPoint) => x(new Date(point.time * MS_PER_SECOND))
  const py = (point: SeriesPoint) => y(point.value)
  const tipX = px(last)
  const tipY = py(last)
  const badgeLabel = formatValue(last.value)
  const badgeWidth = badgeLabel.length * BADGE_CHAR_WIDTH + BADGE_PADDING * 2

  return (
    <svg width={width} height={height} role="presentation">
      <LinearGradient id={gradientId} from={colour} to={colour} fromOpacity={0.3} toOpacity={0} />
      <Group left={MARGIN.left} top={MARGIN.top}>
        <GridRows
          scale={y}
          width={innerWidth}
          numTicks={Y_TICKS}
          stroke="var(--chart-grid)"
          strokeDasharray="2 3"
        />
        {y.ticks(Y_TICKS).map((tick) => (
          <text
            key={tick}
            x={-8}
            y={y(tick)}
            dy="0.32em"
            textAnchor="end"
            fill="var(--chart-label)"
            fontSize={11}
            fontFamily="var(--font-mono)"
          >
            {formatValue(tick)}
          </text>
        ))}
        {x.ticks(xTickCount(innerWidth)).map((tick, index, ticks) => (
          <text
            key={tick.valueOf()}
            x={x(tick)}
            y={innerHeight + 16}
            textAnchor={index === 0 ? 'start' : index === ticks.length - 1 ? 'end' : 'middle'}
            fill="var(--chart-label)"
            fontSize={11}
            fontFamily="var(--font-mono)"
          >
            {formatClock(tick)}
          </text>
        ))}

        <Area<SeriesPoint>
          data={[...points]}
          x={px}
          y0={() => innerHeight}
          y1={py}
          curve={curveMonotoneX}
          fill={`url(#${gradientId})`}
          fillOpacity={AREA_OPACITY}
        />
        <LinePath<SeriesPoint> data={[...points]} x={px} y={py} curve={curveMonotoneX}>
          {({ path }) => (
            <motion.path
              d={path([...points]) ?? undefined}
              fill="none"
              stroke={colour}
              strokeWidth={LINE_WIDTH}
              strokeLinecap="round"
              initial={reduced ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={springTransition('drift', reduced)}
            />
          )}
        </LinePath>

        {/* The live tip: where the series is right now, with its value. */}
        <motion.circle
          cx={tipX}
          cy={tipY}
          r={TIP_RADIUS * 2.4}
          fill={colour}
          animate={reduced ? { opacity: 0.15 } : { opacity: [0.28, 0.06, 0.28] }}
          transition={
            reduced
              ? { duration: 0 }
              : { duration: PULSE_SECONDS, repeat: Number.POSITIVE_INFINITY, ease: 'easeInOut' }
          }
        />
        <circle
          cx={tipX}
          cy={tipY}
          r={TIP_RADIUS}
          fill={colour}
          stroke="var(--bx-surface)"
          strokeWidth={1.5}
        />
        <g transform={`translate(${tipX + 8},${tipY})`}>
          <rect
            x={0}
            y={-BADGE_HEIGHT / 2}
            width={badgeWidth}
            height={BADGE_HEIGHT}
            rx={4}
            fill="var(--bx-elevated)"
            stroke="var(--bx-line-strong)"
          />
          <text
            x={BADGE_PADDING}
            y={0}
            dy="0.32em"
            fill="var(--bx-text)"
            fontSize={11}
            fontWeight={500}
            fontFamily="var(--font-mono)"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {badgeLabel}
          </text>
        </g>
      </Group>
    </svg>
  )
}

interface TraceChartProps {
  readonly points: readonly SeriesPoint[]
  readonly colour: string
  /** Shared across every trace on the page: the comparison is the point. */
  readonly domainMax: number
  readonly formatValue: (value: number) => string
}

/**
 * One model's call rate over the window.
 *
 * Built here rather than on the vendored live-line chart, which computes its own
 * y-domain per chart (so two traces silently sat on different scales), anchors
 * its right edge on `Date.now()` (so a snapshot a minute old trailed off flat),
 * and faded its only two axis labels out at the plot edges.
 */
export function TraceChart({ points, colour, domainMax, formatValue }: TraceChartProps) {
  const gradientId = `trace-${useId().replace(/:/g, '')}`
  return (
    <ParentSize debounceTime={10}>
      {({ width, height }) => (
        <Plot
          width={width}
          height={height}
          points={points}
          colour={colour}
          domainMax={domainMax}
          formatValue={formatValue}
          gradientId={gradientId}
        />
      )}
    </ParentSize>
  )
}
