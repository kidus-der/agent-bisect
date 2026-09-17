import { QueryClient, type UseQueryResult, useQuery } from '@tanstack/react-query'

import { ApiError, type ApiResult, type Schemas, apiFetch } from './client'

const STALE_TIME_MS = 30_000
const MAX_RETRIES = 2

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) return false
  return error instanceof ApiError ? error.retryable : false
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: STALE_TIME_MS, retry: shouldRetry, refetchOnWindowFocus: false },
    },
  })
}

export type MetaPayload = Readonly<Schemas['MetaPayload']>

export const queryKeys = {
  meta: ['meta'] as const,
} as const

export function useMetaQuery(): UseQueryResult<ApiResult<MetaPayload>, ApiError> {
  return useQuery<ApiResult<MetaPayload>, ApiError>({
    queryKey: queryKeys.meta,
    queryFn: ({ signal }) => apiFetch<MetaPayload>('/meta', { signal }),
    // The shell's data-source flag should not spin forever when the API is down.
    retry: false,
  })
}
