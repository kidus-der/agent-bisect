/**
 * `/api/runs` — the run list, paged.
 *
 * Every filter this page offers is the server's: `q`, `fault_type`, `domain`,
 * `outcome`, `status` and `model`, sorted by one of `run_sorting`'s fields.
 * `meta.total` is the count after all of them, so the result line and the
 * pagination both describe the whole corpus, not just the rows loaded so far.
 */
import {
  type UseInfiniteQueryResult,
  type UseQueryResult,
  useInfiniteQuery,
  useQuery,
} from '@tanstack/react-query'

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

/** `none` selects runs with no planted fault; the server rejects anything else. */
export const NO_FAULT = 'none'
export type FaultFilter = FaultType | typeof NO_FAULT
export const FAULT_FILTERS = [...FAULT_TYPES, NO_FAULT] as const satisfies readonly FaultFilter[]

/** `Q_MAX_LENGTH` on the route: a longer query is a 422, so it never gets sent. */
export const QUERY_MAX_CHARS = 100

export interface ServerRunFilters {
  /** Free text over run id, task id, model and tool names. */
  readonly q: string
  readonly fault: FaultFilter | null
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
  if (filters.q) params.set('q', filters.q.slice(0, QUERY_MAX_CHARS))
  if (filters.fault) params.set('fault_type', filters.fault)
  if (filters.domain) params.set('domain', filters.domain)
  if (filters.outcome) params.set('outcome', filters.outcome)
  if (filters.status) params.set('status', filters.status)
  if (filters.model) params.set('model', filters.model)
  return params.toString()
}

export const runsKeys = {
  list: (filters: ServerRunFilters) => ['runs', filters] as const,
  sample: (limit: number) => ['runs', 'sample', limit] as const,
}

/**
 * A short slice of the run list for the Overview strip. `/api/runs` has no
 * recency sort — there is no timestamp among `SORTABLE_RUN_FIELDS` — so this is
 * a stable sample by id, and the UI does not claim these are the latest runs.
 */
export function useRunSampleQuery(
  limit: number,
): UseQueryResult<ApiResult<RunListPage | NotAvailable>, ApiError> {
  return useQuery<ApiResult<RunListPage | NotAvailable>, ApiError>({
    queryKey: runsKeys.sample(limit),
    queryFn: ({ signal }) =>
      apiFetch<RunListPage | NotAvailable>(`/runs?limit=${limit}&sort=-n_steps`, { signal }),
  })
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
