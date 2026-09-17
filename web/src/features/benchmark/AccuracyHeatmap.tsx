import { motion, useReducedMotion } from 'motion/react'
import { useId, useMemo, useState } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { SegmentedControl } from '@/components/primitives/SegmentedControl'
import { useTheme } from '@/design/theme'
import { springTransition } from '@/design/motion'
import { formatPercent, wilsonInterval } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { FaultType, HeatmapCell, MethodName } from './api'
import { HeatmapTable } from './HeatmapTable'
import { HEATMAP_STEPS, heatmapRamp, rampDomain, rampStep } from './heatmapScale'
import { FAULT_TYPE_LABELS, METHOD_ORDER, methodLabel, methodMeta } from './methods'

type HeatmapView = 'matrix' | 'table'

const VIEW_OPTIONS = [
  { value: 'matrix', label: 'Matrix' },
  { value: 'table', label: 'Table' },
] as const

const CELL_ENTER_STAGGER_S = 0.012

/** `judge/step` -> two stacked lines, so a 44px column header stays readable. */
function headerLines(shortLabel: string): readonly string[] {
  return shortLabel.split(/[\s/]+/)
}

/** One line wherever the column is wide enough for it. */
function headerSingleLine(shortLabel: string): string {
  return headerLines(shortLabel).join('·')
}

interface MatrixProps {
  readonly faultTypes: readonly FaultType[]
  readonly methods: readonly MethodName[]
  readonly cellAt: (fault: FaultType, method: MethodName) => HeatmapCell | undefined
  readonly ramp: readonly string[]
  readonly domain: { readonly min: number; readonly max: number }
  readonly onHover: (cell: HeatmapCell | null) => void
}

function Matrix({ faultTypes, methods, cellAt, ramp, domain, onHover }: MatrixProps) {
  const reduced = useReducedMotion() ?? false
  return (
    <div
      aria-hidden="true"
      data-slot="accuracy-matrix"
      onMouseLeave={() => onHover(null)}
      className="grid min-w-0 gap-1 [--label-width:5.5rem] sm:[--label-width:9rem]"
      style={{
        gridTemplateColumns: `var(--label-width) repeat(${methods.length}, minmax(2.5rem, 1fr))`,
      }}
    >
      <span />
      {methods.map((method) => (
        <span
          key={method}
          className="flex flex-col items-center justify-end pb-1 text-center label-instrument leading-3"
        >
          <span className="sm:hidden">
            {headerLines(methodMeta(method).shortLabel).map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </span>
          <span className="hidden sm:inline">
            {headerSingleLine(methodMeta(method).shortLabel)}
          </span>
        </span>
      ))}

      {faultTypes.map((fault, rowIndex) => (
        <FaultRow
          key={fault}
          fault={fault}
          rowIndex={rowIndex}
          methods={methods}
          cellAt={cellAt}
          ramp={ramp}
          domain={domain}
          onHover={onHover}
          reduced={reduced}
        />
      ))}
    </div>
  )
}

interface FaultRowProps extends Omit<MatrixProps, 'faultTypes'> {
  readonly fault: FaultType
  readonly rowIndex: number
  readonly reduced: boolean
}

function FaultRow({
  fault,
  rowIndex,
  methods,
  cellAt,
  ramp,
  domain,
  onHover,
  reduced,
}: FaultRowProps) {
  const sample = methods.map((method) => cellAt(fault, method)).find(Boolean)
  return (
    <>
      <span className="flex min-w-0 flex-col justify-center pr-2">
        <span className="truncate text-small font-medium text-ink">{FAULT_TYPE_LABELS[fault]}</span>
        {sample ? <span className="num text-[11px] text-ink-muted">n = {sample.n}</span> : null}
      </span>
      {methods.map((method, columnIndex) => {
        const cell = cellAt(fault, method)
        if (!cell) {
          return (
            <span
              key={method}
              className="flex h-12 items-center justify-center rounded-step border border-line-strong hatch text-[11px] text-ink-muted sm:h-14"
            >
              n/a
            </span>
          )
        }
        const step = rampStep(cell.accuracy, domain)
        return (
          <motion.span
            key={method}
            initial={reduced ? undefined : { opacity: 0, scale: 0.94 }}
            whileInView={reduced ? undefined : { opacity: 1, scale: 1 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{
              ...springTransition('settle', reduced),
              delay: reduced ? 0 : (rowIndex * methods.length + columnIndex) * CELL_ENTER_STAGGER_S,
            }}
            data-slot="matrix-cell"
            onMouseEnter={() => onHover(cell)}
            style={{ background: ramp[step] }}
            className={cn(
              'flex h-12 items-center justify-center rounded-step num text-small font-semibold text-ink sm:h-14',
              step === HEATMAP_STEPS - 1 && 'ring-1 ring-measure/50 ring-inset',
            )}
          >
            {formatPercent(cell.accuracy, 0)}
          </motion.span>
        )
      })}
    </>
  )
}

interface LegendProps {
  readonly ramp: readonly string[]
  readonly domain: { readonly min: number; readonly max: number }
}

function RampLegend({ ramp, domain }: LegendProps) {
  return (
    <div className="flex shrink-0 items-center gap-2 text-[12px] text-ink-muted">
      <span className="num">{formatPercent(domain.min, 0)}</span>
      <span aria-hidden="true" className="flex gap-0.5">
        {ramp.map((fill) => (
          <span key={fill} style={{ background: fill }} className="h-3 w-4 rounded-[2px]" />
        ))}
      </span>
      <span className="num">{formatPercent(domain.max, 0)}</span>
    </div>
  )
}

interface AccuracyHeatmapProps {
  readonly cells: readonly HeatmapCell[]
}

/** Accuracy for every fault type × method, with the value printed in each cell. */
export function AccuracyHeatmap({ cells }: AccuracyHeatmapProps) {
  const [view, setView] = useState<HeatmapView>('matrix')
  const [hovered, setHovered] = useState<HeatmapCell | null>(null)
  const { theme } = useTheme()
  const captionId = useId()

  const ramp = useMemo(() => heatmapRamp(theme), [theme])
  const domain = useMemo(() => rampDomain(cells.map((cell) => cell.accuracy)), [cells])
  const index = useMemo(() => {
    const map = new Map<string, HeatmapCell>()
    for (const cell of cells) map.set(`${cell.fault_type}|${cell.method}`, cell)
    return map
  }, [cells])

  const faultTypes = useMemo(() => {
    const seen = new Set<FaultType>()
    for (const cell of cells) seen.add(cell.fault_type)
    return [...seen].sort((a, b) => FAULT_TYPE_LABELS[a].localeCompare(FAULT_TYPE_LABELS[b]))
  }, [cells])
  const methods = useMemo(() => {
    const seen = new Set<MethodName>()
    for (const cell of cells) seen.add(cell.method)
    return METHOD_ORDER.filter((method) => seen.has(method))
  }, [cells])

  const cellAt = (fault: FaultType, method: MethodName) => index.get(`${fault}|${method}`)
  const caption = 'Blame accuracy by planted fault type and method, with 95% Wilson intervals.'

  return (
    <Panel variant="chart" bodyClassName="flex flex-col gap-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <InstrumentLabel>accuracy_by_fault</InstrumentLabel>
          <h3 className="text-h3 text-ink">Which faults each method can find</h3>
        </div>
        {/* Secondary to the cost histogram's method picker: two controls of the
            same weight on one page read as one system (direction.md §4). */}
        <SegmentedControl
          label="Accuracy matrix view"
          options={VIEW_OPTIONS}
          value={view}
          onChange={setView}
          size="sm"
        />
      </header>

      <p id={captionId} className="sr-only">
        {caption}
      </p>

      {view === 'matrix' ? (
        <Matrix
          faultTypes={faultTypes}
          methods={methods}
          cellAt={cellAt}
          ramp={ramp}
          domain={domain}
          onHover={setHovered}
        />
      ) : null}

      <HeatmapTable
        faultTypes={faultTypes}
        methods={methods}
        cellAt={cellAt}
        caption={caption}
        hidden={view === 'matrix'}
      />

      {view === 'matrix' ? (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line pt-3">
          <CellReadout cell={hovered} />
          <RampLegend ramp={ramp} domain={domain} />
        </div>
      ) : null}
    </Panel>
  )
}

/** One shared readout instead of twenty tooltips; the table carries the same numbers. */
function CellReadout({ cell }: { readonly cell: HeatmapCell | null }) {
  if (!cell) {
    return (
      <p className="text-[12px] text-ink-muted">
        Hover a cell for its interval. Every value is also in the table view.
      </p>
    )
  }
  const interval = wilsonInterval(cell.accuracy, cell.n)
  return (
    <p className="min-w-0 truncate text-[12px] text-ink-muted">
      <span className="text-ink">{methodLabel(cell.method)}</span> ·{' '}
      {FAULT_TYPE_LABELS[cell.fault_type]} —{' '}
      <span className="num text-ink">{formatPercent(cell.accuracy)}</span>{' '}
      {interval ? (
        <span className="num">
          95% CI [{formatPercent(interval.low)}, {formatPercent(interval.high)}]
        </span>
      ) : null}{' '}
      <span className="num">n = {cell.n}</span>
    </p>
  )
}
