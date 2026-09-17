import { DataTable, type DataTableColumn } from '@/components/primitives/DataTable'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { formatPercent, formatPoints } from '@/lib/stats'

import { deltaBarGeometry } from './deltaBarGeometry'
import { cn } from '@/lib/utils'

import type { ScenarioRow } from './api'

const TABLE_MAX_HEIGHT = 380
const WORSE_THRESHOLD = -0.0001
/**
 * One width for the bars and for the key above them. They are not stacked in the
 * same column, so the key has to be recognisable as a key rather than an axis —
 * sharing the track width is what lets a reader match the two by eye.
 */
const TRACK_WIDTH = 'w-40'

function delta(row: ScenarioRow): number {
  return row.head_pass_rate - row.base_pass_rate
}

/**
 * A bar either side of a centre zero line, scaled against the largest change in
 * the suite — so the longest bar is the worst scenario and every other bar is
 * readable against it. Scaled against the full 0-100 range instead, every row
 * drew the same stub and the mark encoded nothing.
 */
function DeltaBar({ value, scale }: { readonly value: number; readonly scale: number }) {
  const worse = value < WORSE_THRESHOLD
  const bar = deltaBarGeometry(value, scale)
  return (
    <span aria-hidden="true" className={cn('relative inline-block h-4 align-middle', TRACK_WIDTH)}>
      {/* Anchored on the axis midpoint the header declares: the side says the
          sign, the length says the size. */}
      <span
        className={cn(
          'absolute top-1/2 h-2.5 -translate-y-1/2',
          worse ? 'rounded-l-step bg-fail' : 'rounded-r-step bg-pass',
        )}
        style={{ left: `${bar.left}%`, width: `${bar.width}%` }}
      />
      <span className="absolute inset-y-0 left-1/2 z-10 w-px bg-ink-muted" />
    </span>
  )
}

/** The key to the bars: where the zero line is, and what a full-length bar means. */
function DeltaAxisLegend({ scale }: { readonly scale: number }) {
  return (
    <span className="flex items-center gap-2 text-[12px] text-ink-muted">
      <InstrumentLabel>scale</InstrumentLabel>
      <span className="num">−{formatPoints(scale, 0).replace(/^[+−]/, '')}</span>
      <span aria-hidden="true" className={cn('relative inline-block h-3', TRACK_WIDTH)}>
        <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line-strong" />
        <span className="absolute inset-y-0 left-1/2 w-px bg-ink-muted" />
      </span>
      <span className="num">+{formatPoints(scale, 0).replace(/^[+−]/, '')}</span>
    </span>
  )
}

function buildColumns(scale: number): ReadonlyArray<DataTableColumn<ScenarioRow>> {
  return [
    {
      id: 'scenario',
      header: 'scenario',
      sortValue: (row) => row.scenario,
      cell: (row) => <span className="num text-ink">{row.scenario}</span>,
    },
    {
      id: 'delta',
      header: 'change',
      numeric: true,
      sortValue: (row) => delta(row),
      cell: (row) => {
        const value = delta(row)
        const worse = value < WORSE_THRESHOLD
        return (
          <span className="inline-flex items-center justify-end gap-2">
            <DeltaBar value={value} scale={scale} />
            <span className={cn('w-20 num', worse ? 'text-fail' : 'text-pass')}>
              <span aria-hidden="true">{worse ? '▼' : '▲'}</span> {formatPoints(value, 0)}
            </span>
          </span>
        )
      },
    },
    {
      id: 'base',
      header: 'base',
      numeric: true,
      sortValue: (row) => row.base_pass_rate,
      cell: (row) => (
        <span className="num text-ink-muted">{formatPercent(row.base_pass_rate, 0)}</span>
      ),
    },
    {
      id: 'head',
      header: 'head',
      numeric: true,
      sortValue: (row) => row.head_pass_rate,
      cell: (row) => <span className="num text-ink">{formatPercent(row.head_pass_rate, 0)}</span>,
    },
    {
      id: 'n',
      header: 'runs',
      numeric: true,
      hideOnMobile: true,
      sortValue: (row) => row.n,
      cell: (row) => <span className="num text-ink-muted">{row.n}</span>,
    },
  ]
}

/** The largest absolute change in the suite; every bar is drawn against it. */
function deltaScale(scenarios: readonly ScenarioRow[]): number {
  return scenarios.reduce((largest, row) => Math.max(largest, Math.abs(delta(row))), 0)
}

interface ScenarioTableProps {
  readonly scenarios: readonly ScenarioRow[]
}

export function ScenarioTable({ scenarios }: ScenarioTableProps) {
  const worse = scenarios.filter((row) => delta(row) < WORSE_THRESHOLD).length
  return (
    <Panel variant="card" bodyClassName="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <InstrumentLabel>scenarios</InstrumentLabel>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="text-h3 text-ink">Every scenario in the suite</h3>
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <DeltaAxisLegend scale={deltaScale(scenarios)} />
            <span className="num text-small text-ink-muted">
              {worse} of {scenarios.length} worse on head
            </span>
          </span>
        </div>
      </header>
      {scenarios.length === 0 ? (
        <p className="py-6 text-ink-muted">This check ran no scenarios.</p>
      ) : (
        <DataTable
          columns={buildColumns(deltaScale(scenarios))}
          rows={scenarios}
          getRowId={(row) => row.scenario}
          caption="Pass rate per scenario on base and head, with the change between them."
          maxHeight={TABLE_MAX_HEIGHT}
          initialSort={{ columnId: 'delta', direction: 'asc' }}
        />
      )}
    </Panel>
  )
}
