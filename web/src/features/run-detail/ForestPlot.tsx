import { scaleLinear } from '@visx/scale'
import { motion, useReducedMotion } from 'motion/react'
import { useMemo, memo } from 'react'
import useMeasure from 'react-use-measure'

import { STAGGER_SECONDS, springTransition } from '@/design/motion'
import { formatEffect, formatInterval } from '@/lib/format'
import { cn } from '@/lib/utils'

import type { ForestRow } from './blame'

const ROW_HEIGHT = 20
const POINT_SIZE = 9
const CAP_HALF = 5
const AXIS_HEIGHT = 18
const MIN_PLOT_WIDTH = 120
const AXIS_TICKS = 5

type Scale = (value: number) => number

interface ForestRowViewProps {
  readonly row: ForestRow
  readonly x: Scale
  readonly width: number
  readonly selected: boolean
  readonly onSelect: (step: number) => void
  readonly delay: number
  readonly reduced: boolean
}

function rowLabel(row: ForestRow): string {
  const verdict = row.blamed
    ? ', the earliest step clearing the threshold'
    : row.clears
      ? ', clears the threshold'
      : ''
  return `Step ${row.step}, effect ${formatEffect(row.effect)}, 95% interval ${formatEffect(row.low)} to ${formatEffect(row.high)}${verdict}`
}

function ForestRowView({ row, x, width, selected, onSelect, delay, reduced }: ForestRowViewProps) {
  // A gradient in objectBoundingBox units has nothing to resolve against on a
  // zero-height line, so the blamed whisker painted as nothing. Solid amber.
  const stroke = row.blamed ? 'var(--bx-blame)' : 'var(--bx-measure)'
  const fill = row.blamed ? 'var(--bx-blame)' : 'var(--bx-measure)'
  const mid = ROW_HEIGHT / 2
  const estimateX = x(row.effect)
  const grow = { ...springTransition('settle', reduced), delay: reduced ? 0 : delay }

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(row.step)}
        aria-pressed={selected}
        aria-label={rowLabel(row)}
        className="relative flex w-full cursor-pointer items-center gap-3 rounded-step py-0.5 text-left"
      >
        {selected ? (
          <motion.span
            layoutId="forest-selected-row"
            transition={springTransition('snap', reduced)}
            className="absolute -inset-x-1 inset-y-0 rounded-step border border-line-strong bg-elevated"
          />
        ) : null}
        <span
          className={cn(
            'relative w-14 shrink-0 num text-small whitespace-nowrap',
            row.blamed ? 'font-semibold text-blame' : 'text-ink-muted',
          )}
        >
          step {row.step}
        </span>
        <svg
          aria-hidden="true"
          width={width}
          height={ROW_HEIGHT}
          viewBox={`0 0 ${width} ${ROW_HEIGHT}`}
          className="relative shrink-0 overflow-visible"
        >
          <motion.g
            style={{ transformBox: 'view-box', transformOrigin: `${estimateX}px ${mid}px` }}
            initial={reduced ? false : { scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={grow}
          >
            <line
              data-whisker="span"
              x1={x(row.low)}
              x2={x(row.high)}
              y1={mid}
              y2={mid}
              stroke={stroke}
              strokeWidth={2}
            />
            {[row.low, row.high].map((bound) => (
              <line
                key={bound}
                data-whisker="cap"
                x1={x(bound)}
                x2={x(bound)}
                y1={mid - CAP_HALF}
                y2={mid + CAP_HALF}
                stroke={stroke}
                strokeWidth={2}
              />
            ))}
          </motion.g>
          <motion.rect
            x={estimateX - POINT_SIZE / 2}
            y={mid - POINT_SIZE / 2}
            width={POINT_SIZE}
            height={POINT_SIZE}
            rx={1}
            fill={fill}
            stroke="var(--bx-surface)"
            style={{ transformBox: 'view-box', transformOrigin: `${estimateX}px ${mid}px` }}
            initial={reduced ? false : { scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ ...grow, delay: reduced ? 0 : delay + 0.06 }}
          />
        </svg>
        <span className="relative hidden w-44 shrink-0 num text-small whitespace-nowrap md:block">
          <span className={cn('font-semibold', row.blamed ? 'text-blame' : 'text-ink')}>
            {formatEffect(row.effect)}
          </span>{' '}
          <span className="text-ink-muted">{formatInterval(row.low, row.high)}</span>
        </span>
      </button>
    </li>
  )
}

interface ForestAxisProps {
  readonly x: Scale
  readonly width: number
  readonly domain: readonly [number, number]
}

function ForestAxis({ x, width, domain }: ForestAxisProps) {
  const ticks = useMemo(() => {
    const [min, max] = domain
    return Array.from({ length: AXIS_TICKS }, (_, i) => min + ((max - min) * i) / (AXIS_TICKS - 1))
  }, [domain])
  return (
    <svg
      aria-hidden="true"
      width={width}
      height={AXIS_HEIGHT}
      viewBox={`0 0 ${width} ${AXIS_HEIGHT}`}
      className="overflow-visible"
    >
      <line x1={0} x2={width} y1={0.5} y2={0.5} stroke="var(--bx-line)" />
      {ticks.map((tick) => (
        <text
          key={tick}
          x={x(tick)}
          y={12}
          textAnchor="middle"
          className="fill-[var(--bx-muted)] num text-[10px]"
        >
          {formatEffect(tick, 1)}
        </text>
      ))}
    </svg>
  )
}

interface ForestPlotProps {
  readonly rows: readonly ForestRow[]
  readonly domain: readonly [number, number]
  readonly delta: number
  readonly selectedStep: number
  readonly onSelectStep: (step: number) => void
}

/**
 * One row per tested step: a square estimate inside its 95% interval, against a
 * solid zero line and the dashed delta the blame rule uses.
 */
function ForestPlotImpl({ rows, domain, delta, selectedStep, onSelectStep }: ForestPlotProps) {
  const reduced = useReducedMotion() ?? false
  const [plotRef, plotBounds] = useMeasure({ debounce: 0 })
  const width = Math.max(plotBounds.width, MIN_PLOT_WIDTH)
  const x = useMemo(
    () => scaleLinear<number>({ domain: [...domain], range: [0, width] }),
    [domain, width],
  )
  // The blamed row enters last, so it reads as "found", not "one of many".
  const lastDelay = Math.max(rows.length - 1, 0) * STAGGER_SECONDS.forest

  return (
    <div>
      <div className="relative pt-6">
        {/* Zero and delta are drawn once behind every row, so they read as one axis. */}
        <div
          ref={plotRef}
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute top-0 right-0 bottom-0 left-[4.25rem]',
            'md:right-[11.75rem]',
          )}
        >
          <span className="absolute inset-y-0 w-px bg-ink-muted" style={{ left: x(0) }} />
          <span
            className="absolute inset-y-0 border-l border-dashed border-ink-muted"
            style={{ left: x(delta) }}
          />
          <span
            className="absolute top-0 rounded-[3px] bg-surface px-1 num text-[10px] whitespace-nowrap text-ink-muted"
            style={{ left: x(delta) + 3 }}
          >
            δ {delta.toFixed(2)}
          </span>
        </div>
        {/* A 60-step run has 60 rows: cap the list and keep the axis in view below it. */}
        <div className="relative max-h-[26rem] overflow-y-auto">
          <ul className="flex flex-col">
            {rows.map((row, index) => (
              <ForestRowView
                key={row.step}
                row={row}
                x={x}
                width={width}
                selected={row.step === selectedStep}
                onSelect={onSelectStep}
                delay={
                  row.blamed ? lastDelay + STAGGER_SECONDS.forest : index * STAGGER_SECONDS.forest
                }
                reduced={reduced}
              />
            ))}
          </ul>
        </div>
        <div className="pl-[4.25rem] md:pr-[11.75rem]">
          <ForestAxis x={x} width={width} domain={domain} />
        </div>
      </div>
      <table className="sr-only">
        <caption>Per-step causal effect with its 95% confidence interval</caption>
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col">Effect</th>
            <th scope="col">Interval low</th>
            <th scope="col">Interval high</th>
            <th scope="col">Clears δ {delta.toFixed(2)}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.step}>
              <th scope="row">{row.step}</th>
              <td>{formatEffect(row.effect)}</td>
              <td>{formatEffect(row.low)}</td>
              <td>{formatEffect(row.high)}</td>
              <td>{row.clears ? 'yes' : 'no'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Memoised: a rewind tick re-renders the page several times a second, and none
 * of this panel's inputs change while the tape is replaying.
 */
export const ForestPlot = memo(ForestPlotImpl)
