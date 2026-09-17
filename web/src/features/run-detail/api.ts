/**
 * The six `/api/runs/...` endpoints the Run detail page reads
 * (docs/design/api-contract.md). Every hook returns the unwrapped envelope, so
 * `meta.simulated` stays available to the page that has to admit it.
 */
import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type Schemas, apiFetch } from '@/api/client'

export type RunDetail = Readonly<Schemas['RunDetail']>
export type StepView = Readonly<Schemas['StepView']>
export type StepEffect = Readonly<Schemas['StepEffectView']>
export type RunEstimate = Readonly<Schemas['RunEstimateView']>
export type JudgePanel = Readonly<Schemas['JudgePanel']>
export type JudgeRankEntry = Readonly<Schemas['JudgeRankEntry']>
export type RerunRow = Readonly<Schemas['RerunRow']>
export type StepPayload = Readonly<Schemas['StepPayload']>
export type InterventionDiff = Readonly<Schemas['InterventionDiff']>
export type StateDiff = Readonly<Schemas['StateDiff']>
export type DiffEntry = Readonly<Schemas['DiffEntry']>
export type NotAvailable = Readonly<Schemas['NotAvailable']>

/** The two judge protocols the panel compares. */
export type JudgeProtocol = keyof JudgePanel

function segment(value: string): string {
  return encodeURIComponent(value)
}

export const runDetailPaths = {
  detail: (runId: string): string => `/runs/${segment(runId)}`,
  step: (runId: string, stepIdx: number): string => `/runs/${segment(runId)}/steps/${stepIdx}`,
  interventionDiff: (runId: string, stepIdx: number): string =>
    `${runDetailPaths.step(runId, stepIdx)}/intervention-diff`,
  stateDiff: (runId: string, stepIdx: number): string =>
    `${runDetailPaths.step(runId, stepIdx)}/state-diff`,
  reruns: (runId: string): string => `/runs/${segment(runId)}/reruns`,
  rerunSteps: (runId: string, rerunId: string): string =>
    `/runs/${segment(runId)}/reruns/${segment(rerunId)}/steps`,
} as const

export const runDetailKeys = {
  detail: (runId: string) => ['run', runId] as const,
  step: (runId: string, stepIdx: number) => ['run', runId, 'step', stepIdx] as const,
  interventionDiff: (runId: string, stepIdx: number) =>
    ['run', runId, 'step', stepIdx, 'intervention-diff'] as const,
  stateDiff: (runId: string, stepIdx: number) =>
    ['run', runId, 'step', stepIdx, 'state-diff'] as const,
  reruns: (runId: string) => ['run', runId, 'reruns'] as const,
  rerunSteps: (runId: string, rerunId: string) => ['run', runId, 'rerun', rerunId] as const,
} as const

/** The server answers `not_available` rather than inventing a number. */
export function isNotAvailable(value: unknown): value is NotAvailable {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { status?: unknown }).status === 'not_available'
  )
}

export function availableOrNull<T>(value: T | NotAvailable | null): T | null {
  if (value === null || isNotAvailable(value)) return null
  return value
}

type Query<T> = UseQueryResult<ApiResult<T>, ApiError>

export function useRunDetailQuery(runId: string): Query<RunDetail> {
  return useQuery<ApiResult<RunDetail>, ApiError>({
    queryKey: runDetailKeys.detail(runId),
    queryFn: ({ signal }) => apiFetch<RunDetail>(runDetailPaths.detail(runId), { signal }),
  })
}

export function useStepQuery(runId: string, stepIdx: number | null): Query<StepPayload> {
  return useQuery<ApiResult<StepPayload>, ApiError>({
    queryKey: runDetailKeys.step(runId, stepIdx ?? -1),
    queryFn: ({ signal }) =>
      apiFetch<StepPayload>(runDetailPaths.step(runId, stepIdx ?? -1), { signal }),
    enabled: stepIdx !== null,
  })
}

export function useInterventionDiffQuery(
  runId: string,
  stepIdx: number | null,
): Query<InterventionDiff | null> {
  return useQuery<ApiResult<InterventionDiff | null>, ApiError>({
    queryKey: runDetailKeys.interventionDiff(runId, stepIdx ?? -1),
    queryFn: ({ signal }) =>
      apiFetch<InterventionDiff | null>(runDetailPaths.interventionDiff(runId, stepIdx ?? -1), {
        signal,
      }),
    enabled: stepIdx !== null,
  })
}

export function useStateDiffQuery(
  runId: string,
  stepIdx: number | null,
): Query<StateDiff | NotAvailable> {
  return useQuery<ApiResult<StateDiff | NotAvailable>, ApiError>({
    queryKey: runDetailKeys.stateDiff(runId, stepIdx ?? -1),
    queryFn: ({ signal }) =>
      apiFetch<StateDiff | NotAvailable>(runDetailPaths.stateDiff(runId, stepIdx ?? -1), {
        signal,
      }),
    enabled: stepIdx !== null,
  })
}

interface RerunPage {
  readonly reruns: readonly RerunRow[]
}

export function useRerunsQuery(runId: string): Query<RerunPage | NotAvailable> {
  return useQuery<ApiResult<RerunPage | NotAvailable>, ApiError>({
    queryKey: runDetailKeys.reruns(runId),
    queryFn: ({ signal }) =>
      apiFetch<RerunPage | NotAvailable>(runDetailPaths.reruns(runId), { signal }),
  })
}

export function useRerunStepsQuery(
  runId: string,
  rerunId: string,
): Query<readonly StepView[] | NotAvailable> {
  return useQuery<ApiResult<readonly StepView[] | NotAvailable>, ApiError>({
    queryKey: runDetailKeys.rerunSteps(runId, rerunId),
    queryFn: ({ signal }) =>
      apiFetch<readonly StepView[] | NotAvailable>(runDetailPaths.rerunSteps(runId, rerunId), {
        signal,
      }),
  })
}
