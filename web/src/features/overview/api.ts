/**
 * `/api/overview` — the headline result, the KPI block, the recall@m curve, the
 * cost-vs-accuracy points and the hero run (docs/design/api-contract.md).
 *
 * The endpoint answers `not_available` in real mode before anything has been
 * evaluated, so the hook hands back the raw union and the page narrows it.
 */
import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type NotAvailable, type Schemas, apiFetch } from '@/api/client'

export type OverviewPayload = Readonly<Schemas['OverviewPayload']>
export type HeadlineResult = Readonly<Schemas['HeadlineResult']>
export type CiValue = Readonly<Schemas['CiValue']>
export type Kpis = Readonly<Schemas['Kpis']>
export type RecallPoint = Readonly<Schemas['RecallPoint']>
export type CostAccuracyPoint = Readonly<Schemas['CostAccuracyPoint']>
export type RunSummary = Readonly<Schemas['RunSummary']>
export type MethodName = CostAccuracyPoint['method']

export const OVERVIEW_PATH = '/overview'

export const overviewKeys = {
  overview: ['overview'] as const,
} as const

export function useOverviewQuery(): UseQueryResult<
  ApiResult<OverviewPayload | NotAvailable>,
  ApiError
> {
  return useQuery<ApiResult<OverviewPayload | NotAvailable>, ApiError>({
    queryKey: overviewKeys.overview,
    queryFn: ({ signal }) =>
      apiFetch<OverviewPayload | NotAvailable>(OVERVIEW_PATH, { signal }),
  })
}

/** Human labels for the five methods the benchmark compares. */
export const METHOD_LABELS: Readonly<Record<MethodName, string>> = {
  bisect: 'Bisect',
  judge_all_at_once: 'Judge · all at once',
  judge_step_by_step: 'Judge · step by step',
  rerun_live: 'Re-run live',
  no_control: 'No control',
} as const

export function methodLabel(method: MethodName): string {
  return METHOD_LABELS[method]
}
