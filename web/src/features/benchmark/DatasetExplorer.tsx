import { Link } from '@tanstack/react-router'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { useId, useMemo, useState } from 'react'

import { AsyncSection } from '@/components/primitives/AsyncSection'
import { DataTable, type DataTableColumn } from '@/components/primitives/DataTable'
import { EmptyState } from '@/components/primitives/EmptyState'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { Skeleton, TableSkeleton } from '@/components/primitives/Skeleton'
import { formatPercent } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { DatasetEntry, DatasetPage } from './api'
import { useDatasetQuery } from './api'
import { FilterSelect } from './FilterSelect'
import {
  ANY,
  type DatasetFilters,
  EMPTY_FILTERS,
  applyFilters,
  domainsIn,
  hasActiveFilters,
} from './datasetFilters'
import { FAULT_TYPE_LABELS, POSITION_LABELS, POSITION_ORDER } from './methods'

const PAGE_SIZE = 50
const FIRST_PAGE = 1
const TABLE_MAX_HEIGHT = 420

export const INJECT_COMMAND = 'bisect inject --out data/faults.parquet'

const FAULT_OPTIONS = Object.entries(FAULT_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}))
const POSITION_OPTIONS = POSITION_ORDER.map((value) => ({
  value,
  label: POSITION_LABELS[value],
}))
const SPLIT_OPTIONS = [
  { value: 'dev', label: 'dev' },
  { value: 'test', label: 'test' },
]

function RateCell({ rate, tone }: { readonly rate: number; readonly tone: 'base' | 'faulted' }) {
  return (
    <span className={cn('num', tone === 'faulted' ? 'text-fail' : 'text-ink')}>
      {formatPercent(rate, 0)}
    </span>
  )
}

const COLUMNS: ReadonlyArray<DataTableColumn<DatasetEntry>> = [
  {
    id: 'run_id',
    header: 'run',
    width: '13rem',
    sortValue: (row) => row.run_id,
    cell: (row) => (
      <Link
        to="/runs/$runId"
        params={{ runId: row.run_id }}
        className="num text-measure underline-offset-2 hover:underline"
      >
        {row.run_id}
      </Link>
    ),
  },
  {
    id: 'domain',
    header: 'domain',
    sortValue: (row) => row.domain,
    cell: (row) => <span className="text-ink-muted">{row.domain}</span>,
  },
  {
    id: 'task',
    header: 'task',
    hideOnMobile: true,
    sortValue: (row) => row.task_id,
    cell: (row) => <span className="num text-ink">{row.task_id}</span>,
  },
  {
    id: 'fault',
    header: 'fault',
    sortValue: (row) => row.fault_type,
    cell: (row) => (
      <span className="rounded-pill border border-line-strong bg-elevated px-2 py-0.5 text-[12px] whitespace-nowrap text-ink">
        {FAULT_TYPE_LABELS[row.fault_type]}
      </span>
    ),
  },
  {
    id: 'planted_step',
    header: 'step',
    numeric: true,
    hideOnMobile: true,
    sortValue: (row) => row.planted_step,
    cell: (row) => <span className="num text-ink">{row.planted_step}</span>,
  },
  {
    id: 'position',
    header: 'position',
    hideOnMobile: true,
    sortValue: (row) => POSITION_ORDER.indexOf(row.position_bucket),
    cell: (row) => <span className="text-ink-muted">{POSITION_LABELS[row.position_bucket]}</span>,
  },
  {
    id: 'split',
    header: 'split',
    hideOnMobile: true,
    sortValue: (row) => row.split,
    cell: (row) => <span className="num text-ink-muted">{row.split}</span>,
  },
  {
    id: 'base_pass_rate',
    header: 'base pass',
    numeric: true,
    sortValue: (row) => row.base_pass_rate,
    cell: (row) => <RateCell rate={row.base_pass_rate} tone="base" />,
  },
  {
    id: 'faulted_pass_rate',
    header: 'faulted pass',
    numeric: true,
    sortValue: (row) => row.faulted_pass_rate,
    cell: (row) => <RateCell rate={row.faulted_pass_rate} tone="faulted" />,
  },
]

interface FilterBarProps {
  readonly filters: DatasetFilters
  readonly domains: readonly string[]
  readonly onChange: (next: DatasetFilters) => void
}

function FilterBar({ filters, domains, onChange }: FilterBarProps) {
  const searchId = useId()
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <div className="col-span-2 flex min-w-0 flex-col gap-1 sm:col-span-1">
        <label htmlFor={searchId} className="label-instrument">
          search
        </label>
        <div className="relative">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
          />
          <input
            id={searchId}
            type="search"
            value={filters.query}
            placeholder="run or task id"
            onChange={(event) => onChange({ ...filters, query: event.target.value })}
            className="h-8 w-full rounded-control border border-line bg-ground pr-2 pl-8 num text-small text-ink placeholder:text-ink-muted"
          />
        </div>
      </div>
      <FilterSelect
        label="fault type"
        anyLabel="all fault types"
        value={filters.faultType}
        options={FAULT_OPTIONS}
        onChange={(value) =>
          onChange({ ...filters, faultType: value as DatasetFilters['faultType'] })
        }
      />
      <FilterSelect
        label="position"
        anyLabel="anywhere"
        value={filters.position}
        options={POSITION_OPTIONS}
        onChange={(value) =>
          onChange({ ...filters, position: value as DatasetFilters['position'] })
        }
      />
      <FilterSelect
        label="split"
        anyLabel="dev + test"
        value={filters.split}
        options={SPLIT_OPTIONS}
        onChange={(value) => onChange({ ...filters, split: value as DatasetFilters['split'] })}
      />
      <FilterSelect
        label="domain"
        anyLabel="all domains"
        value={filters.domain}
        options={domains.map((domain) => ({ value: domain, label: domain }))}
        onChange={(value) => onChange({ ...filters, domain: value })}
      />
    </div>
  )
}

interface PagerProps {
  readonly page: number
  readonly total: number | null
  readonly shown: number
  readonly onPage: (page: number) => void
}

function Pager({ page, total, shown, onPage }: PagerProps) {
  const lastPage = total === null ? page : Math.max(FIRST_PAGE, Math.ceil(total / PAGE_SIZE))
  const button =
    'inline-flex h-8 items-center gap-1 rounded-control border border-line-strong bg-elevated px-2.5 text-small text-ink disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
      <p className="num text-[12px] text-ink-muted">
        {shown} shown · page {page} of {lastPage}
        {total === null ? '' : ` · ${total} labelled failures`}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={button}
          disabled={page <= FIRST_PAGE}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft aria-hidden="true" className="size-3.5" />
          Previous
        </button>
        <button
          type="button"
          className={button}
          disabled={page >= lastPage}
          onClick={() => onPage(page + 1)}
        >
          Next
          <ChevronRight aria-hidden="true" className="size-3.5" />
        </button>
      </div>
    </div>
  )
}

function DatasetSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-8 w-full" />
      <TableSkeleton rows={8} />
    </div>
  )
}

interface DatasetBodyProps {
  readonly page: DatasetPage
  readonly total: number | null
  readonly pageNumber: number
  readonly onPage: (page: number) => void
}

function DatasetBody({ page, total, pageNumber, onPage }: DatasetBodyProps) {
  const [filters, setFilters] = useState<DatasetFilters>(EMPTY_FILTERS)
  const domains = useMemo(() => domainsIn(page.entries), [page.entries])
  const rows = useMemo(() => applyFilters(page.entries, filters), [page.entries, filters])

  if (page.entries.length === 0) {
    return (
      <EmptyState
        label="no labelled failures"
        title="Nothing has been planted yet"
        description="The dataset is built by breaking successful runs on purpose: plant one fault, re-run, and keep it only if the run flips to failing."
        command={INJECT_COMMAND}
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <FilterBar filters={filters} domains={domains} onChange={setFilters} />
      {rows.length === 0 ? (
        <div className="flex flex-col items-start gap-3 py-8">
          <InstrumentLabel>no rows match</InstrumentLabel>
          <p className="max-w-prose text-ink-muted">
            No labelled failure on this page matches those filters. Clear them, or page through the
            rest of the set.
          </p>
          <button
            type="button"
            onClick={() => setFilters(EMPTY_FILTERS)}
            className="inline-flex h-8 items-center rounded-control border border-line-strong bg-elevated px-3 text-small text-ink"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <DataTable
          columns={COLUMNS}
          rows={rows}
          getRowId={(row) => row.run_id}
          caption="Labelled failures: one planted fault per recorded run."
          maxHeight={TABLE_MAX_HEIGHT}
          initialSort={{ columnId: 'run_id', direction: 'asc' }}
        />
      )}
      <Pager
        page={pageNumber}
        total={hasActiveFilters(filters) ? null : total}
        shown={rows.length}
        onPage={onPage}
      />
    </div>
  )
}

/** The labelled-failure set behind every number on this page. */
export function DatasetExplorer() {
  const [pageNumber, setPageNumber] = useState(FIRST_PAGE)
  const query = useDatasetQuery(pageNumber, PAGE_SIZE)

  return (
    <Panel
      variant="card"
      label="dataset"
      title="Every labelled failure"
      bodyClassName="flex flex-col gap-4"
    >
      <AsyncSection
        query={query}
        subject="the labelled-failure dataset"
        skeleton={<DatasetSkeleton />}
        notMeasured={{
          label: 'dataset',
          title: 'No faults have been planted',
          command: INJECT_COMMAND,
        }}
      >
        {(page, meta) => (
          <DatasetBody
            page={page}
            total={meta.total ?? null}
            pageNumber={pageNumber}
            onPage={setPageNumber}
          />
        )}
      </AsyncSection>
    </Panel>
  )
}

export { ANY }
