import type { DataTableColumn } from '@/components/primitives/DataTable'
import { formatPercent, formatPoints } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { ScenarioRow } from './api'
import { DeltaBar, WORSE_THRESHOLD, scenarioDelta } from './deltaMarks'

/**
 * The suite table's columns, wide and narrow.
 *
 * At 390 the wide set does not fit, and the table simply scrolled the numbers
 * off the right edge — a row read as a scenario name and a coloured bar, which
 * states nothing a reader can quote. The narrow set therefore keeps the change
 * itself, pairs the two pass rates into one `93% → 26%` cell, and drops the run
 * count, which is constant across the suite and stated in the panel above.
 */
function DeltaValue({ value }: { readonly value: number }) {
  const worse = value < WORSE_THRESHOLD
  return (
    <span className={cn('num whitespace-nowrap', worse ? 'text-fail' : 'text-pass')}>
      <span aria-hidden="true">{worse ? '▼' : '▲'}</span> {formatPoints(value, 0)}
    </span>
  )
}

/** Base and head in one cell: the pair is the reading, and it survives at 390. */
function PassPair({ row }: { readonly row: ScenarioRow }) {
  return (
    <span className="num whitespace-nowrap text-ink-muted">
      {formatPercent(row.base_pass_rate, 0)}
      <span aria-hidden="true">→</span>
      <span className="text-ink">{formatPercent(row.head_pass_rate, 0)}</span>
    </span>
  )
}

export function scenarioColumns(
  scale: number,
  narrow: boolean,
): ReadonlyArray<DataTableColumn<ScenarioRow>> {
  const scenario: DataTableColumn<ScenarioRow> = {
    id: 'scenario',
    header: 'scenario',
    sortValue: (row) => row.scenario,
    cell: (row) => (
      // At 390 the name wraps rather than truncating. Every scenario in a suite
      // shares a long prefix, so an ellipsis after eight characters would make
      // all 24 rows read the same; wrapping costs height and keeps them apart.
      <span
        className={cn('num text-ink', narrow && 'block max-w-[5rem] break-all whitespace-normal')}
      >
        {row.scenario}
      </span>
    ),
  }

  const delta: DataTableColumn<ScenarioRow> = {
    id: 'delta',
    header: 'change',
    numeric: true,
    sortValue: (row) => scenarioDelta(row),
    cell: (row) =>
      narrow ? (
        // No bar: the track needs 10rem it does not have here, and the signed
        // number is the part that carries the reading.
        <DeltaValue value={scenarioDelta(row)} />
      ) : (
        <span className="inline-flex items-center justify-end gap-2">
          <DeltaBar value={scenarioDelta(row)} scale={scale} />
          <span className="w-20">
            <DeltaValue value={scenarioDelta(row)} />
          </span>
        </span>
      ),
  }

  if (narrow) {
    return [
      scenario,
      delta,
      {
        id: 'pass',
        header: 'base → head',
        numeric: true,
        sortValue: (row) => row.head_pass_rate,
        cell: (row) => <PassPair row={row} />,
      },
    ]
  }

  return [
    scenario,
    delta,
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
