import { curveMonotoneX } from '@visx/curve'
import { GridRows } from '@visx/grid'
import { Group } from '@visx/group'
import { ParentSize } from '@visx/responsive'
import { scaleLinear, scalePoint } from '@visx/scale'
import { Area, LinePath } from '@visx/shape'
import { motion, useReducedMotion } from 'motion/react'

import { roleColour } from '@/components/chart-theme/chartTheme'
import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { springTransition } from '@/design/motion'
import { formatPercent } from '@/lib/stats'

import type { PositionAccuracy, PositionBucket } from './api'
import { POSITION_LABELS, POSITION_ORDER, methodLabel, methodMeta } from './methods'
import {
  type PositionPoint,
  type PositionSeries,
  buildPositionSeries,
  positionDomain,
} from './positionSeries'

const MIN_PLOT_HEIGHT = 160
const MARGIN = { top: 16, right: 92, bottom: 30, left: 44 } as const
const Y_TICKS = 4
const POINT_RADIUS = 4
const BAND_OPACITY = 0.16
const LINE_WIDTH = 2
const LABEL_MIN_GAP = 16
const WHISKER_CAP = 4

type XScale = ReturnType<typeof scalePoint<PositionBucket>>
type YScale = ReturnType<typeof scaleLinear<number>>

interface SeriesLayerProps {
  readonly series: PositionSeries
  readonly index: number
  readonly x: XScale
  readonly y: YScale
  readonly reduced: boolean
}

function SeriesLayer({ series, index, x, y, reduced }: SeriesLayerProps) {
  const colour = roleColour(methodMeta(series.method).role)
  const banded = series.points.filter((point) => point.interval !== null)
  const px = (point: PositionPoint) => x(point.position) ?? 0
  const transition = {
    ...springTransition('drift', reduced),
    delay: reduced ? 0 : index * 0.08,
  }

  return (
    <Group>
      {banded.length > 1 ? (
        <Area<PositionPoint>
          data={banded}
          x={px}
          y0={(point) => y(point.interval?.low ?? point.accuracy)}
          y1={(point) => y(point.interval?.high ?? point.accuracy)}
          curve={curveMonotoneX}
          fill={colour}
          fillOpacity={BAND_OPACITY}
          stroke="none"
        />
      ) : null}
      {/* Per-point whiskers: the band shows the shape, these show each bucket's own n. */}
      {series.points.map((point) =>
        point.interval ? (
          <Group key={`whisker-${point.position}`} opacity={0.65}>
            <line
              x1={px(point)}
              x2={px(point)}
              y1={y(point.interval.low)}
              y2={y(point.interval.high)}
              stroke={colour}
              strokeWidth={1}
            />
            {[point.interval.low, point.interval.high].map((bound) => (
              <line
                key={bound}
                x1={px(point) - WHISKER_CAP}
                x2={px(point) + WHISKER_CAP}
                y1={y(bound)}
                y2={y(bound)}
                stroke={colour}
                strokeWidth={1}
              />
            ))}
          </Group>
        ) : null,
      )}
      <LinePath<PositionPoint>
        data={[...series.points]}
        x={px}
        y={(point) => y(point.accuracy)}
        curve={curveMonotoneX}
      >
        {({ path }) => (
          <motion.path
            d={path([...series.points]) ?? undefined}
            fill="none"
            stroke={colour}
            strokeWidth={LINE_WIDTH}
            strokeLinecap="round"
            initial={reduced ? undefined : { pathLength: 0 }}
            whileInView={reduced ? undefined : { pathLength: 1 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={transition}
          />
        )}
      </LinePath>
      {series.points.map((point) => (
        <circle
          key={point.position}
          cx={px(point)}
          cy={y(point.accuracy)}
          r={POINT_RADIUS}
          fill={colour}
          stroke="var(--bx-surface)"
          strokeWidth={1.5}
        />
      ))}
    </Group>
  )
}

interface PlotProps {
  readonly width: number
  readonly height: number
  readonly series: readonly PositionSeries[]
}

function Plot({ width, height, series }: PlotProps) {
  const reduced = useReducedMotion() ?? false
  const innerWidth = Math.max(0, width - MARGIN.left - MARGIN.right)
  const innerHeight = Math.max(MIN_PLOT_HEIGHT, height) - MARGIN.top - MARGIN.bottom
  if (innerWidth <= 0) return null

  const x = scalePoint<PositionBucket>({
    domain: [...POSITION_ORDER],
    range: [0, innerWidth],
    padding: 0.18,
  })
  // The CI envelope with a 10% pad, not a fixed 80-100 window: with every band
  // inside a few points of the others, a fixed floor left the plot mostly empty.
  const drawn = positionDomain(series)
  const y = scaleLinear<number>({
    domain: [drawn.min, drawn.max],
    range: [innerHeight, 0],
    nice: true,
  })

  // Direct labels beat a legend here, but they must not collide.
  const labels = series
    .map((entry) => ({
      method: entry.method,
      value: entry.points.at(-1)?.accuracy ?? 0,
      colour: roleColour(methodMeta(entry.method).role),
    }))
    .sort((a, b) => b.value - a.value)
  const placed = labels.reduce<ReadonlyArray<(typeof labels)[number] & { readonly at: number }>>(
    (placedSoFar, label) => {
      const previous = placedSoFar.at(-1)?.at ?? Number.NEGATIVE_INFINITY
      const at = Math.max(y(label.value), previous + LABEL_MIN_GAP)
      return [...placedSoFar, { ...label, at }]
    },
    [],
  )

  return (
    <svg width={width} height={innerHeight + MARGIN.top + MARGIN.bottom} role="presentation">
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
            {formatPercent(tick, 0)}
          </text>
        ))}
        {POSITION_ORDER.map((position) => (
          <text
            key={position}
            x={x(position) ?? 0}
            y={innerHeight + 20}
            textAnchor="middle"
            fill="var(--chart-label)"
            fontSize={11}
            fontFamily="var(--font-mono)"
          >
            {POSITION_LABELS[position]}
          </text>
        ))}
        {series.map((entry, index) => (
          <SeriesLayer
            key={entry.method}
            series={entry}
            index={index}
            x={x}
            y={y}
            reduced={reduced}
          />
        ))}
        {placed.map((label) => (
          <text
            key={label.method}
            x={innerWidth + 10}
            y={label.at}
            dy="0.32em"
            fill={label.colour}
            fontSize={12}
            fontWeight={600}
          >
            {methodLabel(label.method)}
          </text>
        ))}
      </Group>
    </svg>
  )
}

function describe(series: readonly PositionSeries[]): string {
  const sentences = series.map((entry) => {
    const parts = entry.points.map(
      (point) =>
        `${POSITION_LABELS[point.position]} ${formatPercent(point.accuracy)} (95% CI ${
          point.interval
            ? `${formatPercent(point.interval.low)} to ${formatPercent(point.interval.high)}`
            : 'not computable'
        }, n=${point.n})`,
    )
    return `${methodLabel(entry.method)}: ${parts.join('; ')}.`
  })
  return `Blame accuracy by where the fault was planted in the run. ${sentences.join(' ')}`
}

interface PositionSlopeProps {
  readonly rows: readonly PositionAccuracy[]
}

/** Accuracy against where in the run the fault sits, with a Wilson band per method. */
export function PositionSlope({ rows }: PositionSlopeProps) {
  const series = buildPositionSeries(rows)
  const onlyOne = series.length === 1
  return (
    <ChartFrame
      label="accuracy_by_position"
      title="Accuracy by fault position"
      description={describe(series)}
      heightClassName="h-[264px]"
    >
      <div className="flex h-full min-w-0 flex-col">
        <ParentSize debounceTime={10} className="min-h-0 flex-1">
          {({ width, height }) => <Plot width={width} height={height} series={series} />}
        </ParentSize>
        <p className="shrink-0 pt-1 text-[12px] text-ink-muted">
          Shaded: 95% Wilson interval from n per bucket.
          {onlyOne
            ? ` Only ${methodLabel(series[0]?.method ?? 'bisect')} was broken down by position in this evaluation.`
            : ''}
        </p>
      </div>
    </ChartFrame>
  )
}
