import { Link } from '@tanstack/react-router'
import { ChevronRight } from 'lucide-react'

import { AsyncSection } from '@/components/primitives/AsyncSection'
import { DataTable, type DataTableColumn } from '@/components/primitives/DataTable'
import { EmptyState } from '@/components/primitives/EmptyState'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { Skeleton, TableSkeleton } from '@/components/primitives/Skeleton'
import { formatPValue, formatPercent, formatPoints, newcombeInterval } from '@/lib/stats'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/pages/PageHeader'

import { GATE_COMMAND, type PrCheckSummary, usePrChecksQuery } from './api'

/** The list endpoint has no run count; the suite is 24 scenarios x 4 runs. */
const RUNS_PER_REF = 96
const TABLE_MAX_HEIGHT = 460
const MOBILE_ROW_HEIGHT = 76

function change(check: PrCheckSummary): number {
  return check.head_pass_rate - check.base_pass_rate
}

function VerdictChip({ check }: { readonly check: PrCheckSummary }) {
  const regressed = check.is_regression
  return (
    <span
      data-verdict={regressed ? 'regression' : 'clean'}
      className={cn(
        'inline-flex items-center gap-1 rounded-pill border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap',
        regressed
          ? 'border-fail/40 bg-fail-tint text-fail'
          : 'border-pass/40 bg-pass-tint text-pass',
      )}
    >
      <span aria-hidden="true">{regressed ? '✕' : '✓'}</span>
      {regressed ? 'regression' : 'clean'}
    </span>
  )
}

/** An estimate never appears without its interval — including in a list. */
function DeltaCell({ check }: { readonly check: PrCheckSummary }) {
  const delta = change(check)
  const interval = newcombeInterval(
    check.head_pass_rate,
    RUNS_PER_REF,
    check.base_pass_rate,
    RUNS_PER_REF,
  )
  // Colour is spent only when the interval excludes zero. A +4 point change
  // whose interval runs from −7 to +15 is not an improvement worth colouring.
  const decisive = interval !== null && (interval.low > 0 || interval.high < 0)
  return (
    <span className="inline-flex flex-col items-end">
      <span
        className={cn(
          'num text-small',
          !decisive ? 'text-ink-muted' : delta < 0 ? 'text-fail' : 'text-pass',
        )}
      >
        {formatPoints(delta, 0)}
      </span>
      {interval ? (
        <span className="num text-[11px] text-ink-muted">
          <span className="sr-only">95% confidence interval </span>[{formatPoints(interval.low, 0)},{' '}
          {formatPoints(interval.high, 0)}]
        </span>
      ) : null}
    </span>
  )
}

const COLUMNS: ReadonlyArray<DataTableColumn<PrCheckSummary>> = [
  {
    id: 'pr',
    header: 'pr · suite',
    sortValue: (row) => row.pr_number,
    // Below `sm` the suite and the verdict have no column of their own, so they
    // stack under the number: the suite name is the row's identity and a
    // verdict carried by colour alone would not be a verdict.
    cell: (row) => (
      <span className="flex flex-col gap-0.5">
        <Link
          to="/pr-checks/$checkId"
          params={{ checkId: row.check_id }}
          className="num text-measure underline-offset-2 hover:underline"
        >
          #{row.pr_number}
        </Link>
        {/* A hard cap, not just `truncate`: the table does not use a fixed
            layout, so an unbounded cell simply widens the row. */}
        <span className="block max-w-[8rem] truncate num text-[12px] text-ink-muted sm:hidden">
          {row.title}
        </span>
        <span className="sm:hidden">
          <VerdictChip check={row} />
        </span>
      </span>
    ),
  },
  {
    id: 'verdict',
    header: 'verdict',
    width: '7rem',
    hideOnMobile: true,
    sortValue: (row) => (row.is_regression ? 0 : 1),
    cell: (row) => <VerdictChip check={row} />,
  },
  {
    id: 'suite',
    header: 'scenario suite',
    hideOnMobile: true,
    sortValue: (row) => row.title,
    cell: (row) => <span className="num text-ink">{row.title}</span>,
  },
  {
    id: 'base',
    header: 'base',
    numeric: true,
    width: '4.5rem',
    hideOnMobile: true,
    sortValue: (row) => row.base_pass_rate,
    cell: (row) => (
      <span className="num text-ink-muted">{formatPercent(row.base_pass_rate, 0)}</span>
    ),
  },
  {
    id: 'head',
    header: 'head',
    numeric: true,
    width: '4.5rem',
    hideOnMobile: true,
    sortValue: (row) => row.head_pass_rate,
    cell: (row) => (
      <span className={cn('num', row.is_regression ? 'text-fail' : 'text-ink')}>
        {formatPercent(row.head_pass_rate, 0)}
      </span>
    ),
  },
  {
    id: 'delta',
    header: 'change · 95% CI',
    numeric: true,
    width: '10rem',
    sortValue: (row) => change(row),
    cell: (row) => <DeltaCell check={row} />,
  },
  {
    id: 'p',
    header: 'p',
    numeric: true,
    width: '4.5rem',
    hideOnMobile: true,
    sortValue: (row) => row.p_value,
    cell: (row) => <span className="num text-ink-muted">{formatPValue(row.p_value)}</span>,
  },
  {
    id: 'open',
    header: '',
    width: '2rem',
    // At 390 the chevron would push the change column off the row; the
    // link-coloured PR number carries the affordance there instead.
    hideOnMobile: true,
    cell: () => <ChevronRight aria-hidden="true" className="size-4 text-ink-muted" />,
  },
]

function ListSkeleton() {
  return (
    <Panel variant="card">
      <Skeleton className="h-3 w-24" />
      <div className="mt-4">
        <TableSkeleton rows={6} />
      </div>
    </Panel>
  )
}

function CheckList({ checks }: { readonly checks: readonly PrCheckSummary[] }) {
  // The stacked mobile cell needs a taller row; above `sm` the default holds.
  const narrow = useMediaQuery('(max-width: 640px)')
  const rowHeight = narrow ? MOBILE_ROW_HEIGHT : undefined
  if (checks.length === 0) {
    return (
      <Panel variant="canvas">
        <EmptyState
          label="no gate results"
          title="No pull request has been gated"
          description="The gate runs the scenario suite on both refs; a drop beyond noise triggers blame on the new failures."
          command={GATE_COMMAND}
        />
      </Panel>
    )
  }
  const regressions = checks.filter((check) => check.is_regression).length
  return (
    <Panel variant="card" bodyClassName="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex flex-col gap-1">
          <InstrumentLabel>gate_results</InstrumentLabel>
          <h2 className="text-h2 text-ink">Every gated pull request</h2>
        </div>
        <div className="flex items-baseline gap-6">
          <span className="flex items-baseline gap-2">
            <span className="num text-stat text-fail">{regressions}</span>
            <InstrumentLabel>flagged</InstrumentLabel>
          </span>
          <span className="flex items-baseline gap-2">
            <span className="num text-stat text-ink">{checks.length - regressions}</span>
            <InstrumentLabel>clean</InstrumentLabel>
          </span>
        </div>
      </header>
      <DataTable
        columns={COLUMNS}
        rows={checks}
        getRowId={(row) => row.check_id}
        caption="Gated pull requests: base and head pass rate on the same scenario suite, with the change and its 95% interval."
        maxHeight={TABLE_MAX_HEIGHT}
        rowHeight={rowHeight}
        initialSort={{ columnId: 'delta', direction: 'asc' }}
      />
    </Panel>
  )
}

export function PrChecksPage() {
  const query = usePrChecksQuery()
  return (
    <>
      <PageHeader
        label="pr checks"
        title="PR checks"
        description="Base vs head on a fixed scenario suite, and the decisive step behind any regression."
      />
      <AsyncSection
        query={query}
        subject="gate results"
        skeleton={<ListSkeleton />}
        notMeasured={{
          label: 'pr checks',
          title: 'No pull request has been gated',
          command: GATE_COMMAND,
        }}
      >
        {(checks) => <CheckList checks={checks} />}
      </AsyncSection>
    </>
  )
}
