import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type Schemas, apiFetch } from '@/api/client'
import { type NotAvailable, splitNotAvailable } from '@/api/payload'

export type BenchmarkSummary = Readonly<Schemas['BenchmarkSummary']>
export type MethodResult = Readonly<Schemas['MethodResult']>
export type MethodName = MethodResult['method']
export type HeatmapCell = Readonly<Schemas['HeatmapCell']>
export type FaultType = HeatmapCell['fault_type']
export type PositionAccuracy = Readonly<Schemas['PositionAccuracy']>
export type PositionBucket = PositionAccuracy['position']
export type SankeyFlow = Readonly<Schemas['SankeyFlow']>
export type BlameLabel = SankeyFlow['label']
export type FlakyAblation = Readonly<Schemas['FlakyAblation']>
export type CostBucket = Readonly<Schemas['CostBucket']>
export type DatasetEntry = Readonly<Schemas['DatasetEntry']>
export type DatasetPage = Readonly<Schemas['DatasetPage']>
export type CiValue = MethodResult['accuracy']

export const benchmarkKeys = {
  summary: ['benchmark', 'summary'] as const,
  dataset: (page: number, limit: number) => ['benchmark', 'dataset', page, limit] as const,
} as const

type SummaryResult = ApiResult<BenchmarkSummary | NotAvailable>

export function useBenchmarkQuery(): UseQueryResult<SummaryResult, ApiError> {
  return useQuery<SummaryResult, ApiError>({
    queryKey: benchmarkKeys.summary,
    queryFn: ({ signal }) =>
      apiFetch<BenchmarkSummary | NotAvailable>('/benchmark', { signal }),
  })
}

type DatasetResult = ApiResult<DatasetPage | NotAvailable>

export function useDatasetQuery(
  page: number,
  limit: number,
): UseQueryResult<DatasetResult, ApiError> {
  return useQuery<DatasetResult, ApiError>({
    queryKey: benchmarkKeys.dataset(page, limit),
    queryFn: ({ signal }) =>
      apiFetch<DatasetPage | NotAvailable>(`/dataset?page=${page}&limit=${limit}`, { signal }),
    placeholderData: (previous) => previous,
  })
}

export { splitNotAvailable }
