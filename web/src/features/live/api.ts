import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type Schemas, apiFetch } from '@/api/client'
import type { NotAvailable } from '@/api/payload'

export type LiveSnapshot = Readonly<Schemas['LiveSnapshot']>
export type CallsPoint = Readonly<Schemas['CallsPoint']>
export type BudgetStatus = Readonly<Schemas['BudgetStatus']>
export type RateLimitStatus = Readonly<Schemas['RateLimitStatus']>
export type JobStatus = Readonly<Schemas['JobStatus']>
export type JobState = JobStatus['state']

export type JobPhase = JobStatus['phase']

export const liveKeys = { snapshot: ['live', 'snapshot'] as const } as const

type SnapshotResult = ApiResult<LiveSnapshot | NotAvailable>

/**
 * The first frame. The stream then replaces it every couple of seconds, so this
 * never refetches on its own — a poll beside a stream would be two sources of
 * truth for the same numbers.
 */
export function useLiveSnapshotQuery(): UseQueryResult<SnapshotResult, ApiError> {
  return useQuery<SnapshotResult, ApiError>({
    queryKey: liveKeys.snapshot,
    queryFn: ({ signal }) => apiFetch<LiveSnapshot | NotAvailable>('/live/snapshot', { signal }),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnMount: false,
  })
}
