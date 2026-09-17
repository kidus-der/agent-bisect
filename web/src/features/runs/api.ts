/**
 * `/api/runs` — the run list, paged.
 *
 * What the server can filter and sort is fixed by the API contract: `domain`,
 * `outcome`, `status` and `model` as filters, and `run_id`, `n_steps`,
 * `cost_usd`, `calls`, `outcome`, `domain` as sort keys. Free text and fault
 * type are not query parameters, so the table narrows those over the rows it
 * has loaded and says so in the result count rather than pretending the server
 * did it.
 */
import { type UseInfiniteQueryResult, useInfiniteQuery } from '@tanstack/react-query'

import {
  type ApiError,
  type ApiResult,
  type NotAvailable,
  type Schemas,
  apiFetch,
} from '@/api/client'

export type RunSummary = Readonly<Schemas['RunSummary']>
export type RunListPage = Readonly<Schemas['RunListPage']>
export type SparkPoint = Readonly<Schemas['SparkPoint']>
export type BlameCell = Readonly<Schemas['BlameCell']>
export type RunOutcome = NonNullable<RunSummary['outcome']>
export type RunStatus = RunSummary['status']
export type FaultType = NonNullable<RunSummary['fault_type']>

/** Big enough that the 266-run fixture is two requests, small enough to paint fast. */
export const RUNS_PAGE_SIZE = 100

/** `run_sorting.SORTABLE_RUN_FIELDS`; anything else the server silently ignores. */
export const SORTABLE_RUN_FIELDS = [
  'run_id',
  'n_steps',
  'cost_usd',
  'calls',
  'outcome',
  'domain',
] as const
export type SortableRunField = (typeof SORTABLE_RUN_FIELDS)[number]

export const FAULT_TYPES = [
  'wrong_value',
  'missing_field',
  'stale_record',
  'tool_error',
] as const satisfies readonly FaultType[]

export interface ServerRunFilters {
  readonly domain: string | null
  readonly outcome: RunOutcome | null
  readonly status: RunStatus | null
  readonly model: string | null
  readonly sort: SortableRunField
  readonly descending: boolean
}

export function runsQueryString(filters: ServerRunFilters, page: number): string {
  const params = new URLSearchParams({
    sort: `${filters.descending ? '-' : ''}${filters.sort}`,
    page: String(page),
    limit: String(RUNS_PAGE_SIZE),
  })
  if (filters.domain) params.set('domain', filters.domain)
  if (filters.outcome) params.set('outcome', filters.outcome)
  if (filters.status) params.set('status', filters.status)
  if (filters.model) params.set('model', filters.model)
  return params.toString()
}

export const runsKeys = {
  list: (filters: ServerRunFilters) => ['runs', filters] as const,
}

type RunsPage = ApiResult<RunListPage | NotAvailable>

/** `page * limit < total` is the only "is there more" signal; `next_cursor` is always null. */
export function nextPageParam(lastPage: RunsPage): number | undefined {
  const { total, page, limit } = lastPage.meta
  if (total == null || page == null || limit == null) return undefined
  return page * limit < total ? page + 1 : undefined
}

export type RunsQuery = UseInfiniteQueryResult<
  { readonly pages: readonly RunsPage[]; readonly pageParams: readonly unknown[] },
  ApiError
>

export function useRunsQuery(filters: ServerRunFilters): RunsQuery {
  return useInfiniteQuery({
    queryKey: runsKeys.list(filters),
    initialPageParam: 1,
    queryFn: ({ pageParam, signal }) =>
      apiFetch<RunListPage | NotAvailable>(`/runs?${runsQueryString(filters, pageParam)}`, {
        signal,
      }),
    getNextPageParam: nextPageParam,
  }) as RunsQuery
}
