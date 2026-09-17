/**
 * `/api/overview` — the headline result, the KPI block, the recall@m curve, the
 * cost-vs-accuracy points and the hero run (docs/design/api-contract.md).
 *
 * The endpoint answers `not_available` in real mode before anything has been
 * evaluated, so the hook hands back the raw union and the page narrows it.
 */
import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import {
  type ApiError,
  type ApiResult,
  type NotAvailable,
  type Schemas,
  apiFetch,
} from '@/api/client'

export type OverviewPayload = Readonly<Schemas['OverviewPayload']>
export type HeadlineResult = Readonly<Schemas['HeadlineResult']>
export type CiValue = Readonly<Schemas['CiValue']>
export type Kpis = Readonly<Schemas['Kpis']>
export type RecallPoint = Readonly<Schemas['RecallPoint']>
export type CostAccuracyPoint = Readonly<Schemas['CostAccuracyPoint']>
export type RunSummary = Readonly<Schemas['RunSummary']>
export type MethodName = CostAccuracyPoint['method']
export type BenchmarkSummary = Readonly<Schemas['BenchmarkSummary']>
export type MethodResult = Readonly<Schemas['MethodResult']>

export const OVERVIEW_PATH = '/overview'
export const BENCHMARK_PATH = '/benchmark'

export const overviewKeys = {
  overview: ['overview'] as const,
  benchmark: ['benchmark'] as const,
} as const

export function useOverviewQuery(): UseQueryResult<
  ApiResult<OverviewPayload | NotAvailable>,
  ApiError
> {
  return useQuery<ApiResult<OverviewPayload | NotAvailable>, ApiError>({
    queryKey: overviewKeys.overview,
    queryFn: ({ signal }) => apiFetch<OverviewPayload | NotAvailable>(OVERVIEW_PATH, { signal }),
  })
}

/**
 * The Overview's `cost_vs_accuracy` points carry a bare accuracy; the intervals
 * for the same five methods live on `/api/benchmark`. The scatter reads them
 * from there rather than plotting a point estimate with no interval — and
 * degrades to "intervals unavailable" if this request fails.
 */
export function useBenchmarkMethodsQuery(): UseQueryResult<
  ApiResult<BenchmarkSummary | NotAvailable>,
  ApiError
> {
  return useQuery<ApiResult<BenchmarkSummary | NotAvailable>, ApiError>({
    queryKey: overviewKeys.benchmark,
    queryFn: ({ signal }) => apiFetch<BenchmarkSummary | NotAvailable>(BENCHMARK_PATH, { signal }),
  })
}

/** Accuracy interval per method, keyed by method name. Empty when none were served. */
export function accuracyIntervals(
  methods: readonly MethodResult[] | null,
): ReadonlyMap<MethodName, CiValue> {
  return new Map((methods ?? []).map((entry) => [entry.method, entry.accuracy]))
}

/**
 * The envelope only promises *a* payload. This checks it is the one this page
 * knows how to draw, so a shape change upstream becomes a stated error rather
 * than a blank screen.
 */
export function isOverviewPayload(value: unknown): value is OverviewPayload {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<OverviewPayload>
  return (
    typeof candidate.headline?.bisect?.value === 'number' &&
    typeof candidate.headline.best_judge?.value === 'number' &&
    typeof candidate.kpis?.runs_recorded === 'number' &&
    Array.isArray(candidate.recall_at_m) &&
    Array.isArray(candidate.cost_vs_accuracy) &&
    typeof candidate.hero_run?.run_id === 'string'
  )
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
