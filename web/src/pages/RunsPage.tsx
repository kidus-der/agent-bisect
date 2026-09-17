import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/api/client'
import { EmptyState } from '@/components/primitives/EmptyState'
import { HeatLegend } from '@/components/primitives/HeatLegend'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'
import { StatePanel } from '@/components/primitives/StatePanel'
import { LoadingRegion } from '@/components/primitives/Skeleton'
import { RunsFilters } from '@/features/runs/RunsFilters'
import { RunsTable } from '@/features/runs/RunsTable'
import type { RunSummary, SortableRunField } from '@/features/runs/api'
import { useRunsQuery } from '@/features/runs/api'
import { runDetailKeys, runDetailPaths } from '@/features/run-detail/api'
import type { RunFacets } from '@/features/runs/runRows'
import {
  EMPTY_FACETS,
  narrowRuns,
  resultSummary,
  runFacets,
  stableFacets,
} from '@/features/runs/runRows'
import {
  type RunsSearch,
  clearFilters,
  hasActiveFilters,
  nextSort,
  serverFilters,
  toSearchParams,
  validateRunsSearch,
} from '@/features/runs/runsSearch'

import { formatEffect } from '@/lib/format'

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
  const queryClient = useQueryClient()
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
  /**
   * Warm the detail on hover or focus. Without it the header mounts ~200ms
   * after the click, by which time the row it should morph from is gone — a
   * shared-layout transition needs both in the same commit.
   */
  const onIntent = useCallback(
    (run: RunSummary) =>
      void queryClient.prefetchQuery({
        queryKey: runDetailKeys.detail(run.run_id),
        queryFn: ({ signal }) => apiFetch(runDetailPaths.detail(run.run_id), { signal }),
      }),
    [queryClient],
  )

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query
  const pageCount = pages.length
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && pageCount < AUTO_PAGE_LIMIT) void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, pageCount])

  const narrowed = useMemo(() => narrowRuns(pages), [pages])
  // A filter that matches nothing must not empty the bar that produced it, so
  // the last non-empty set is remembered. `loadedFacets` is stable per page
  // set, so this settles in one extra render rather than looping.
  const loadedFacets = useMemo(() => runFacets(pages), [pages])
  const [rememberedFacets, setRememberedFacets] = useState<RunFacets>(EMPTY_FACETS)
  const facets = stableFacets(loadedFacets, rememberedFacets)
  if (facets === loadedFacets && rememberedFacets !== loadedFacets) {
    setRememberedFacets(loadedFacets)
  }
  const summary = resultSummary(narrowed, search)
  const filtered = hasActiveFilters(search)

  const header = (
    <PageHeader
      label="runs"
      title="Runs"
      // The content here is the list; every pixel above it costs a row.
      density="compact"
      description="Open one to scrub its tape and see which step carries the blame."
    />
  )

  if (query.isPending) {
    return (
      <>
        {header}
        <LoadingRegion
          subject="runs"
          failureCount={query.failureCount}
          failureMessage={query.failureReason?.message}
        >
          <TableSkeletonPage />
        </LoadingRegion>
      </>
    )
  }

  if (query.isError) {
    return (
      <>
        {header}
        <StatePanel>
          <ErrorState
            title="Cannot load the run list"
            message={query.error.message}
            code={query.error.code}
            onRetry={() => void query.refetch()}
          />
        </StatePanel>
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
          <div className="flex flex-col gap-2.5 border-b border-line px-4 py-3">
            <RunsFilters search={search} facets={facets} onChange={apply} summary={summary} />
            {/* Once per table, not per row. Each row's ramp is its own run's. */}
            {narrowed.rows.length > 0 ? <HeatLegend perRun format={formatEffect} /> : null}
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
              onIntent={onIntent}
              footer={
                narrowed.total === null
                  ? `${narrowed.loaded} shown`
                  : `${narrowed.loaded} of ${narrowed.total}`
              }
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
