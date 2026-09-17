/**
 * What each method costs for the accuracy it buys. visx rather than the
 * vendored Bklit scatter, which takes Date x-values only and has no error-bar
 * or per-point-label support — both of which this plot is mostly made of.
 *
 * Cost spans two orders of magnitude (3¢ to $3), so the x-axis is logarithmic
 * and says so.
 */
import { Group } from '@visx/group'
import { ParentSize } from '@visx/responsive'
import { scaleLinear, scaleLog } from '@visx/scale'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { useRef } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours } from '@/components/chart-theme/chartTheme'
import { springTransition } from '@/design/motion'
import { formatNumber } from '@/lib/format'

import type { CiValue, CostAccuracyPoint, MethodName } from './api'
import { placeLabels } from './labelPlacement'
import { methodLabel } from './api'
import { formatPercent } from './headline'

const MARGIN = { top: 18, right: 28, bottom: 46, left: 44 } as const
const MIN_HEIGHT = 240
/**
 * Accuracies here run 0.67 to 0.99 including their intervals, so the axis starts
 * at 0.5 rather than spending half the plot on empty space. Every tick is
 * labelled, and these are points, not bars — no length is being compared.
 */
const Y_DOMAIN = [0.5, 1] as const
const Y_TICKS = [0.5, 0.6, 0.7, 0.8, 0.9, 1] as const
const X_TICKS = [0.03, 0.1, 0.3, 1, 3] as const
const POINT_RADIUS = 5
const HEADLINE_RADIUS = 7
const CAP_HALF = 4
const POINT_DELAY_SECONDS = 0.07
const IN_VIEW_AMOUNT = 0.3
const MIN_COST_USD = 0.02

/**
 * Colour is a role, not an identity: measurement cyan for the methods that
 * re-run the agent, judge violet for the ones that ask a model. Each point is
 * named in text, so colour never has to carry which method it is.
 */
const JUDGE_METHODS: ReadonlySet<MethodName> = new Set(['judge_all_at_once', 'judge_step_by_step'])

function methodColour(method: MethodName): string {
  return JUDGE_METHODS.has(method) ? chartColours.judge : chartColours.treated
}

function formatCost(value: number): string {
  return formatNumber(value, { decimals: 2, prefix: '$' })
}

export interface ScatterPoint extends CostAccuracyPoint {
  /** The interval from `/api/benchmark`, or null when it was not served. */
  readonly interval: CiValue | null
}

export function toScatterPoints(
  points: readonly CostAccuracyPoint[],
  intervals: ReadonlyMap<MethodName, CiValue>,
): readonly ScatterPoint[] {
  return points.map((point) => ({ ...point, interval: intervals.get(point.method) ?? null }))
}

function describe(points: readonly ScatterPoint[]): string {
  if (points.length === 0) return 'No cost-versus-accuracy points were reported.'
  const sentences = points.map((point) => {
    const interval = point.interval
      ? `, 95% CI ${formatPercent(point.interval.ci_low)} to ${formatPercent(point.interval.ci_high)}`
      : ' (no interval reported)'
    return `${methodLabel(point.method)}: ${formatCost(point.mean_cost_usd)} per diagnosis at ${formatPercent(point.accuracy)} step accuracy${interval}.`
  })
  return `Step accuracy against mean cost per diagnosis, one point per method, cost on a logarithmic axis. ${sentences.join(' ')}`
}

interface PlotProps {
  readonly points: readonly ScatterPoint[]
  readonly width: number
  readonly height: number
  readonly revealed: boolean
  readonly reduced: boolean
}

function Plot({ points, width, height, revealed, reduced }: PlotProps) {
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 0)
  const innerHeight = Math.max(height - MARGIN.top - MARGIN.bottom, 0)
  const costs = points.map((point) => Math.max(point.mean_cost_usd, MIN_COST_USD))
  const x = scaleLog<number>({
    domain: [Math.min(...costs, MIN_COST_USD) * 0.6, Math.max(...costs) * 1.7],
    range: [0, innerWidth],
  })
  const y = scaleLinear<number>({ domain: [...Y_DOMAIN], range: [innerHeight, 0] })
  const pointX = (point: ScatterPoint): number => x(Math.max(point.mean_cost_usd, MIN_COST_USD))
  const labels = new Map(
    placeLabels(
      points.map((point) => ({
        id: point.method,
        x: pointX(point),
        y: y(point.accuracy),
        length: methodLabel(point.method).length,
      })),
      innerWidth,
    ).map((entry) => [entry.id, entry]),
  )

  return (
    <svg width={width} height={height} aria-hidden="true">
      <Group left={MARGIN.left} top={MARGIN.top}>
        {Y_TICKS.map((tick) => (
          <g key={tick}>
            <line x1={0} x2={innerWidth} y1={y(tick)} y2={y(tick)} stroke={chartColours.grid} />
            <text
              x={-10}
              y={y(tick)}
              dy="0.32em"
              textAnchor="end"
              fontSize={11}
              fill={chartColours.label}
              className="num"
            >
              {Math.round(tick * 100)}
            </text>
          </g>
        ))}

        {X_TICKS.map((tick) => (
          <text
            key={tick}
            x={x(tick)}
            y={innerHeight + 18}
            textAnchor="middle"
            fontSize={11}
            fill={chartColours.label}
            className="num"
          >
            {formatCost(tick)}
          </text>
        ))}
        <text
          x={innerWidth / 2}
          y={innerHeight + 36}
          textAnchor="middle"
          fontSize={11}
          fill={chartColours.label}
        >
          mean cost per diagnosis (USD, log scale)
        </text>
        <text
          transform={`translate(${-MARGIN.left + 12} ${innerHeight / 2}) rotate(-90)`}
          textAnchor="middle"
          fontSize={11}
          fill={chartColours.label}
        >
          step accuracy (%)
        </text>

        {points.map((point, index) => {
          const colour = methodColour(point.method)
          const isHeadline = point.method === 'bisect'
          const cx = pointX(point)
          const cy = y(point.accuracy)
          const label = labels.get(point.method)
          return (
            <motion.g
              key={point.method}
              initial={reduced ? false : { opacity: 0, scale: 0.7 }}
              animate={revealed || reduced ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.7 }}
              transition={{
                ...springTransition('settle', reduced),
                delay: reduced ? 0 : index * POINT_DELAY_SECONDS,
              }}
              style={{ transformOrigin: `${cx}px ${cy}px` }}
            >
              {point.interval ? (
                <g stroke={colour} strokeWidth={1.5}>
                  <line
                    x1={cx}
                    x2={cx}
                    y1={y(point.interval.ci_low)}
                    y2={y(point.interval.ci_high)}
                  />
                  <line
                    x1={cx - CAP_HALF}
                    x2={cx + CAP_HALF}
                    y1={y(point.interval.ci_low)}
                    y2={y(point.interval.ci_low)}
                  />
                  <line
                    x1={cx - CAP_HALF}
                    x2={cx + CAP_HALF}
                    y1={y(point.interval.ci_high)}
                    y2={y(point.interval.ci_high)}
                  />
                </g>
              ) : null}
              <circle
                cx={cx}
                cy={cy}
                r={isHeadline ? HEADLINE_RADIUS : POINT_RADIUS}
                fill={isHeadline ? colour : chartColours.background}
                stroke={colour}
                strokeWidth={2}
              />
              {/* Direct labels: no legend to cross-reference. */}
              <text
                x={cx + (label?.dx ?? 0)}
                y={cy + (label?.dy ?? 0)}
                textAnchor={label?.anchor ?? 'start'}
                fontSize={12}
                fontWeight={isHeadline ? 650 : 500}
                fill={isHeadline ? colour : chartColours.foreground}
              >
                {methodLabel(point.method)}
              </text>
            </motion.g>
          )
        })}
      </Group>
    </svg>
  )
}

interface CostAccuracyScatterProps {
  readonly points: readonly ScatterPoint[]
  /** True when `/api/benchmark` could not supply the accuracy intervals. */
  readonly intervalsUnavailable: boolean
}

export function CostAccuracyScatter({ points, intervalsUnavailable }: CostAccuracyScatterProps) {
  const reduced = useReducedMotion() ?? false
  const containerRef = useRef<HTMLDivElement | null>(null)
  const inView = useInView(containerRef, { amount: IN_VIEW_AMOUNT, once: true })

  return (
    <ChartFrame
      label="cost_vs_accuracy"
      title="What the accuracy costs"
      description={describe(points)}
      heightClassName="h-64"
      legend={
        intervalsUnavailable ? (
          <span className="label-instrument">intervals unavailable_</span>
        ) : (
          <span className="label-instrument">whiskers = 95% ci_</span>
        )
      }
    >
      <div ref={containerRef} className="size-full">
        {points.length === 0 ? (
          <p className="flex size-full items-center text-small text-ink-muted">
            No cost-versus-accuracy points reported.
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
