import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type Schemas, apiFetch } from '@/api/client'
import type { NotAvailable } from '@/api/payload'

export type PrCheckSummary = Readonly<Schemas['PrCheckSummary']>
export type PrCheckDetail = Readonly<Schemas['PrCheckDetail']>
export type ScenarioRow = Readonly<Schemas['ScenarioRow']>
export type CiValue = PrCheckDetail['base_pass_rate']

export const prCheckKeys = {
  list: ['pr-checks', 'list'] as const,
  detail: (checkId: string) => ['pr-checks', 'detail', checkId] as const,
} as const

type ListResult = ApiResult<readonly PrCheckSummary[] | NotAvailable>

export function usePrChecksQuery(): UseQueryResult<ListResult, ApiError> {
  return useQuery<ListResult, ApiError>({
    queryKey: prCheckKeys.list,
    queryFn: ({ signal }) =>
      apiFetch<readonly PrCheckSummary[] | NotAvailable>('/pr-checks', { signal }),
  })
}

type DetailResult = ApiResult<PrCheckDetail | NotAvailable>

export function usePrCheckQuery(checkId: string): UseQueryResult<DetailResult, ApiError> {
  return useQuery<DetailResult, ApiError>({
    queryKey: prCheckKeys.detail(checkId),
    queryFn: ({ signal }) =>
      apiFetch<PrCheckDetail | NotAvailable>(`/pr-checks/${encodeURIComponent(checkId)}`, {
        signal,
      }),
  })
}

export const GATE_COMMAND = 'bisect gate --base main --head HEAD'
