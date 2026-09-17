import { GridRows } from '@visx/grid'
import { Group } from '@visx/group'
import { ParentSize } from '@visx/responsive'
import { scaleLinear } from '@visx/scale'
import { motion, useReducedMotion } from 'motion/react'
import { useMemo, useState } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { roleColour } from '@/components/chart-theme/chartTheme'
import { SegmentedControl } from '@/components/primitives/SegmentedControl'
import { springTransition } from '@/design/motion'
import { formatNumber } from '@/lib/format'

import type { CostBucket, MethodName, MethodResult } from './api'
import { fillBinGaps, maxBinCount, totalBinCount } from './costBins'
import { byMethodOrder, methodLabel, methodMeta } from './methods'

const MIN_PLOT_HEIGHT = 170
const MARGIN = { top: 28, right: 16, bottom: 34, left: 40 } as const
const Y_TICKS = 4
const BAR_INSET = 1.5
const FAINT_MARKER_OPACITY = 0.3
const LABEL_FLIP_FRACTION = 0.72

interface PlotProps {
  readonly width: number
  readonly height: number
  readonly bins: readonly CostBucket[]
  readonly methods: readonly MethodResult[]
  readonly selected: MethodName
}

function Plot({ width, height, bins, methods, selected }: PlotProps) {
  const reduced = useReducedMotion() ?? false
  const innerWidth = Math.max(0, width - MARGIN.left - MARGIN.right)
  const innerHeight = Math.max(MIN_PLOT_HEIGHT, height) - MARGIN.top - MARGIN.bottom
  if (innerWidth <= 0 || bins.length === 0) return null

  const maxCalls = Math.max(
    bins[bins.length - 1]?.calls_high ?? 0,
    ...methods.map((method) => method.mean_calls),
  )
  const x = scaleLinear<number>({ domain: [0, maxCalls], range: [0, innerWidth] })
  const y = scaleLinear<number>({
    domain: [0, maxBinCount(bins)],
    range: [innerHeight, 0],
    nice: true,
  })

  const selectedResult = methods.find((method) => method.method === selected)
  const markerTransition = springTransition('glide', reduced)

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
            {tick}
          </text>
        ))}

        {bins.map((bin) => {
          const left = x(bin.calls_low) + BAR_INSET
          const barWidth = Math.max(0, x(bin.calls_high) - x(bin.calls_low) - BAR_INSET * 2)
          const top = y(bin.count)
          return (
            <motion.rect
              key={bin.calls_low}
              x={left}
              width={barWidth}
              rx={2}
              fill="var(--bx-measure-tint)"
              stroke="var(--bx-measure)"
              strokeOpacity={bin.count === 0 ? 0.25 : 0.55}
              initial={reduced ? undefined : { y: innerHeight, height: 0 }}
              whileInView={reduced ? undefined : { y: top, height: Math.max(0, innerHeight - top) }}
              viewport={{ once: true, amount: 0.3 }}
              transition={springTransition('settle', reduced)}
              y={top}
              height={Math.max(0, innerHeight - top)}
            />
          )
        })}

        {/* Every method's mean is drawn; the chosen one is the one that is labelled. */}
        {methods
          .filter((method) => method.method !== selected)
          .map((method) => (
            <line
              key={method.method}
              x1={x(method.mean_calls)}
              x2={x(method.mean_calls)}
              y1={0}
              y2={innerHeight}
              stroke={roleColour(methodMeta(method.method).role)}
              strokeOpacity={FAINT_MARKER_OPACITY}
              strokeDasharray="3 3"
            />
          ))}

        {selectedResult ? (
          <MeanMarker
            x={x(selectedResult.mean_calls)}
            innerWidth={innerWidth}
            innerHeight={innerHeight}
            method={selectedResult}
            transition={markerTransition}
          />
        ) : null}

        {x.ticks(4).map((tick) => (
          <text
            key={tick}
            x={x(tick)}
            y={innerHeight + 20}
            textAnchor="middle"
            fill="var(--chart-label)"
            fontSize={11}
            fontFamily="var(--font-mono)"
          >
            {formatNumber(tick, { decimals: 0 })}
          </text>
        ))}
        <text
          x={innerWidth}
          y={innerHeight + 20}
          textAnchor="end"
          fill="var(--chart-label)"
          fontSize={11}
        >
          model calls
        </text>
      </Group>
    </svg>
  )
}

interface MeanMarkerProps {
  readonly x: number
  readonly innerWidth: number
  readonly innerHeight: number
  readonly method: MethodResult
  readonly transition: ReturnType<typeof springTransition>
}

function MeanMarker({ x, innerWidth, innerHeight, method, transition }: MeanMarkerProps) {
  const colour = roleColour(methodMeta(method.method).role)
  const flip = x / innerWidth > LABEL_FLIP_FRACTION
  return (
    <motion.g animate={{ x }} initial={false} transition={transition}>
      <line y1={-8} y2={innerHeight} stroke={colour} strokeWidth={2} />
      <text
        x={flip ? -8 : 8}
        y={-14}
        textAnchor={flip ? 'end' : 'start'}
        fill={colour}
        fontSize={12}
        fontWeight={600}
      >
        {methodLabel(method.method)} · {formatNumber(method.mean_calls, { decimals: 0 })} calls
      </text>
    </motion.g>
  )
}

interface CostHistogramProps {
  readonly histogram: readonly CostBucket[]
  readonly methods: readonly MethodResult[]
}

/** Distribution of calls per diagnosis, with each method's mean laid over it. */
export function CostHistogram({ histogram, methods }: CostHistogramProps) {
  const ordered = useMemo(() => byMethodOrder(methods), [methods])
  const [selected, setSelected] = useState<MethodName>(ordered[0]?.method ?? 'bisect')
  const bins = useMemo(() => fillBinGaps(histogram), [histogram])
  const total = totalBinCount(bins)

  const options = ordered.map((method) => ({
    value: method.method,
    label: methodMeta(method.method).shortLabel,
  }))

  const description = `Histogram of model calls per diagnosis over ${total} labelled failures, in bins of ${
    (bins[0]?.calls_high ?? 0) - (bins[0]?.calls_low ?? 0)
  } calls. ${ordered
    .map(
      (method) =>
        `${methodLabel(method.method)} averages ${formatNumber(method.mean_calls, { decimals: 0 })} calls at $${method.mean_cost_usd.toFixed(2)}.`,
    )
    .join(' ')}`

  return (
    <ChartFrame
      label="calls_per_diagnosis"
      title="What a diagnosis costs"
      description={description}
      heightClassName="h-80"
      legend={
        <div className="max-w-full min-w-0 overflow-x-auto">
          <SegmentedControl
            label="Method whose mean cost is highlighted"
            options={options}
            value={selected}
            onChange={setSelected}
          />
        </div>
      }
    >
      <ParentSize debounceTime={10}>
        {({ width, height }) => (
          <Plot width={width} height={height} bins={bins} methods={ordered} selected={selected} />
        )}
      </ParentSize>
    </ChartFrame>
  )
}
