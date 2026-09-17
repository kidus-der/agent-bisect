import { useNavigate, useSearch } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo } from 'react'

import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'
import { LoadingRegion } from '@/components/primitives/Skeleton'
import { RunsFilters } from '@/features/runs/RunsFilters'
import { RunsTable } from '@/features/runs/RunsTable'
import type { RunSummary, SortableRunField } from '@/features/runs/api'
import { useRunsQuery } from '@/features/runs/api'
import { narrowRuns, resultSummary, runFacets } from '@/features/runs/runRows'
import {
  type RunsSearch,
  clearFilters,
  hasActiveFilters,
  nextSort,
  serverFilters,
  toSearchParams,
  validateRunsSearch,
} from '@/features/runs/runsSearch'

import { PageHeader } from './PageHeader'
import { TableSkeletonPage } from './skeletons'

/**
 * Pages are fetched ahead so free-text search covers the whole list, but only
 * so far: past this the list keeps a "load more" button rather than pulling an
 * unbounded corpus into the browser.
 */
const AUTO_PAGE_LIMIT = 10

const RECORD_COMMAND = 'bisect record --domain airline --tasks 0-19'

export function RunsPage() {
  const navigate = useNavigate()
  // `strict: false` keeps the page from importing the route that lazy-loads it;
  // the URL is re-validated here anyway, because it is external input.
  const rawSearch = useSearch({ strict: false })
  const search = useMemo(
    () => validateRunsSearch(rawSearch as Record<string, unknown>),
    [rawSearch],
  )

  const filters = useMemo(() => serverFilters(search), [search])
  const query = useRunsQuery(filters)
  const pages = useMemo(() => query.data?.pages ?? [], [query.data])

  const apply = useCallback(
    (next: RunsSearch) =>
      void navigate({ to: '/runs', search: toSearchParams(next), replace: true }),
    [navigate],
  )
  const onSortChange = useCallback(
    (column: SortableRunField) => apply(nextSort(search, column)),
    [apply, search],
  )
  const onOpen = useCallback(
    (run: RunSummary) => void navigate({ to: '/runs/$runId', params: { runId: run.run_id } }),
    [navigate],
  )

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query
  const pageCount = pages.length
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && pageCount < AUTO_PAGE_LIMIT) void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, pageCount])

  const narrowed = useMemo(() => narrowRuns(pages), [pages])
  const facets = useMemo(() => runFacets(pages), [pages])
  const summary = resultSummary(narrowed, search)
  const filtered = hasActiveFilters(search)

  const header = (
    <PageHeader
      label="runs"
      title="Runs"
      description="Every recorded run. Open one to scrub its tape and see which step carries the blame."
    />
  )

  if (query.isPending) {
    return (
      <>
        {header}
        <LoadingRegion subject="runs">
          <TableSkeletonPage />
        </LoadingRegion>
      </>
    )
  }

  if (query.isError) {
    return (
      <>
        {header}
        <Panel variant="card">
          <ErrorState
            title="Cannot load the run list"
            message={query.error.message}
            code={query.error.code}
            onRetry={() => void query.refetch()}
          />
        </Panel>
      </>
    )
  }

  if (narrowed.notAvailable || (narrowed.loaded === 0 && !filtered)) {
    return (
      <>
        {header}
        <Panel variant="canvas">
          <EmptyState
            label="no runs recorded"
            title="The tape is empty"
            description="Record a batch of τ² airline tasks. Each run is written to tape so it can be replayed with zero network calls."
            command={RECORD_COMMAND}
          />
        </Panel>
      </>
    )
  }

  return (
    <>
      {header}
      <div className="flex flex-col gap-4">
        {/* Toolbar and table are one instrument: the filters sit inside the panel they narrow. */}
        <Panel variant="card" className="p-0" bodyClassName="min-w-0">
          <div className="border-b border-line p-4">
            <RunsFilters search={search} facets={facets} onChange={apply} summary={summary} />
          </div>

          {narrowed.rows.length === 0 ? (
            <div className="px-4">
              <EmptyState
                label="no match"
                title="No runs match these filters"
                description="Nothing in the recorded runs matches every filter at once. Widen one, or clear them all and start again."
              >
                <button
                  type="button"
                  onClick={() => apply(clearFilters(search))}
                  className="inline-flex h-9 cursor-pointer items-center rounded-control border border-line-strong bg-elevated px-3 text-small font-medium text-ink hover:border-ink-muted"
                >
                  Clear filters
                </button>
              </EmptyState>
            </div>
          ) : (
            <RunsTable
              rows={narrowed.rows}
              search={search}
              onSortChange={onSortChange}
              onOpen={onOpen}
            />
          )}
        </Panel>

        {hasNextPage ? (
          <div className="flex justify-center">
            <button
              type="button"
              disabled={isFetchingNextPage}
              onClick={() => void fetchNextPage()}
              className="inline-flex h-9 cursor-pointer items-center rounded-control border border-line-strong bg-elevated px-4 text-small font-medium text-ink hover:border-ink-muted disabled:cursor-wait disabled:text-ink-muted"
            >
              {isFetchingNextPage ? 'Loading…' : 'Load more runs'}
            </button>
          </div>
        ) : null}
      </div>
    </>
  )
}
