/**
 * recall@m: how often the judge's top-m shortlist contains the true decisive
 * step. Built on visx rather than the vendored Bklit line chart, whose x-scale
 * accepts Date values only — m is an integer, and faking it as epoch time costs
 * a hand-drawn overlay axis and rules out the pre-registration annotation.
 */
import { curveMonotoneX } from '@visx/curve'
import { Group } from '@visx/group'
import { ParentSize } from '@visx/responsive'
import { scaleLinear } from '@visx/scale'
import { AreaClosed, LinePath } from '@visx/shape'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { useId, useRef } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { PercentYAxis } from '@/components/chart-theme/PercentYAxis'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { springTransition } from '@/design/motion'
import { formatPercent } from '@/lib/stats'

import type { RecallPoint } from './api'

/** δ = 0.10 and m = 3 are pre-registered (docs/decisions/0001-preregistration.md). */
const PREREGISTERED_M = 3
const MARGIN = { top: 16, right: 20, bottom: 40, left: 44 } as const
const MIN_HEIGHT = 240
const Y_TICKS = [0, 0.25, 0.5, 0.75, 1] as const
const MARKER_RADIUS = 3.5
const IN_VIEW_AMOUNT = 0.3
/** Below this the pre-registration note collides with the end label. */
const NARROW_PLOT_PX = 340

function describe(points: readonly RecallPoint[]): string {
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return 'No recall@m points were reported.'
  const preregistered = points.find((point) => point.m === PREREGISTERED_M)
  const middle = preregistered
    ? ` At the pre-registered m=${PREREGISTERED_M} it is ${formatPercent(preregistered.recall)}.`
    : ''
  return (
    `Recall at m, for m from ${first.m} to ${last.m}: the share of failures whose true decisive step ` +
    `appears in the judge's top m suspects. It rises from ${formatPercent(first.recall)} at m=${first.m} ` +
    `to ${formatPercent(last.recall)} at m=${last.m}.${middle} ` +
    'Replay can only confirm a step the shortlist contains, so this is the ceiling on accuracy.'
  )
}

interface PlotProps {
  readonly points: readonly RecallPoint[]
  readonly width: number
  readonly height: number
  readonly revealed: boolean
  readonly reduced: boolean
}

function Plot({ points, width, height, revealed, reduced }: PlotProps) {
  const clipId = useId()
  const gradientId = useId()
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 0)
  const innerHeight = Math.max(height - MARGIN.top - MARGIN.bottom, 0)
  const firstM = points[0]?.m ?? 1
  const lastM = points.at(-1)?.m ?? firstM

  const x = scaleLinear<number>({ domain: [firstM, lastM], range: [0, innerWidth] })
  const y = scaleLinear<number>({ domain: [0, 1], range: [innerHeight, 0] })
  const preregistered = points.find((point) => point.m === PREREGISTERED_M)
  const last = points.at(-1)

  return (
    <svg width={width} height={height} aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={chartColours.treated} stopOpacity={0.28} />
          <stop offset="1" stopColor={chartColours.treated} stopOpacity={0} />
        </linearGradient>
        <clipPath id={clipId}>
          <motion.rect
            x={0}
            y={-MARGIN.top}
            width={innerWidth + MARGIN.right}
            height={height}
            // Springs only, transform only: the clip scales from its left edge on `drift`.
            style={{ originX: 0 }}
            initial={reduced ? false : { scaleX: 0 }}
            animate={{ scaleX: revealed || reduced ? 1 : 0 }}
            transition={springTransition('drift', reduced)}
          />
        </clipPath>
      </defs>
      <Group left={MARGIN.left} top={MARGIN.top}>
        <PercentYAxis ticks={Y_TICKS} scale={y} width={innerWidth} />

        {preregistered ? (
          <g>
            <line
              x1={x(PREREGISTERED_M)}
              x2={x(PREREGISTERED_M)}
              y1={0}
              y2={innerHeight}
              stroke={chartColours.label}
              strokeDasharray="3 3"
            />
            <text
              x={x(PREREGISTERED_M) + 6}
              y={12}
              fontSize={11}
              fill={chartColours.label}
              stroke={chartColours.background}
              strokeWidth={3}
              paintOrder="stroke"
              className="num"
            >
              {innerWidth < NARROW_PLOT_PX
                ? `m=${PREREGISTERED_M}`
                : `m=${PREREGISTERED_M} pre-registered`}
            </text>
          </g>
        ) : null}

        <g clipPath={`url(#${clipId})`}>
          <AreaClosed<RecallPoint>
            data={[...points]}
            x={(point) => x(point.m)}
            y={(point) => y(point.recall)}
            yScale={y}
            curve={curveMonotoneX}
            fill={`url(#${gradientId})`}
          />
          <LinePath<RecallPoint>
            data={[...points]}
            x={(point) => x(point.m)}
            y={(point) => y(point.recall)}
            curve={curveMonotoneX}
            stroke={chartColours.treated}
            strokeWidth={2}
            strokeLinecap="round"
          />
          {points.map((point) => (
            <circle
              key={point.m}
              cx={x(point.m)}
              cy={y(point.recall)}
              r={MARKER_RADIUS}
              fill={chartColours.background}
              stroke={chartColours.treated}
              strokeWidth={1.5}
            />
          ))}
        </g>

        {/* Direct label instead of a legend: the series names itself at its end. */}
        {last ? (
          <text
            x={x(last.m)}
            y={y(last.recall) - 14}
            textAnchor="end"
            fontSize={12}
            fontWeight={600}
            fill={chartColours.treated}
            className="num"
          >
            {formatPercent(last.recall)}
          </text>
        ) : null}

        {points.map((point) => (
          <text
            key={point.m}
            x={x(point.m)}
            y={innerHeight + 18}
            textAnchor="middle"
            fontSize={11}
            fill={chartColours.label}
            className="num"
          >
            {point.m}
          </text>
        ))}
        <text
          x={innerWidth / 2}
          y={innerHeight + 34}
          textAnchor="middle"
          fontSize={11}
          fill={chartColours.label}
        >
          m (suspects the judge shortlists)
        </text>
      </Group>
    </svg>
  )
}

interface RecallCurveProps {
  readonly points: readonly RecallPoint[]
}

export function RecallCurve({ points }: RecallCurveProps) {
  const reduced = useReducedMotion() ?? false
  const containerRef = useRef<HTMLDivElement | null>(null)
  const inView = useInView(containerRef, { amount: IN_VIEW_AMOUNT, once: true })

  return (
    <ChartFrame
      label="recall@m"
      title="Is the culprit even on the shortlist?"
      description={describe(points)}
      heightClassName="h-64"
    >
      <div ref={containerRef} className="size-full">
        {points.length === 0 ? (
          <p className="flex size-full items-center text-small text-ink-muted">
            No recall@m points reported.
          </p>
        ) : (
          <ParentSize debounceTime={0}>
            {({ width, height }) =>
              width === 0 ? null : (
                <Plot
                  points={points}
                  width={width}
                  height={Math.max(height, MIN_HEIGHT)}
                  revealed={inView}
                  reduced={reduced}
                />
              )
            }
          </ParentSize>
        )}
      </div>
    </ChartFrame>
  )
}
