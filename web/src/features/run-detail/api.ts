/**
 * The six `/api/runs/...` endpoints the Run detail page reads
 * (docs/design/api-contract.md). Every hook returns the unwrapped envelope, so
 * `meta.simulated` stays available to the page that has to admit it.
 */
import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type Schemas, apiFetch, isNotAvailable } from '@/api/client'

export type RunDetail = Readonly<Schemas['RunDetail']>
export type StepView = Readonly<Schemas['StepView']>
export type StepEffect = Readonly<Schemas['StepEffectView']>
export type RunEstimate = Readonly<Schemas['RunEstimateView']>
export type EstimatorConfig = Readonly<Schemas['EstimatorConfig']>
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

function asArray<T>(value: unknown): readonly T[] {
  return Array.isArray(value) ? (value as readonly T[]) : []
}

/**
 * The generated types promise these arrays, the network does not. Normalising
 * here means no component has to guard a `.map` on a malformed payload.
 */
export function normalizeRunDetail(raw: RunDetail): RunDetail {
  const estimate = raw.estimate
  const judge = raw.judge
  return {
    ...raw,
    steps: asArray<StepView>(raw.steps) as StepView[],
    estimate: estimate
      ? { ...estimate, step_effects: asArray<StepEffect>(estimate.step_effects) as StepEffect[] }
      : null,
    judge: judge
      ? {
          all_at_once: asArray<JudgeRankEntry>(judge.all_at_once) as JudgeRankEntry[],
          step_by_step: asArray<JudgeRankEntry>(judge.step_by_step) as JudgeRankEntry[],
        }
      : null,
  }
}

export function normalizeStepPayload(raw: StepPayload): StepPayload {
  return {
    ...raw,
    messages: asArray<Record<string, string>>(raw.messages) as Record<string, string>[],
  }
}

export function normalizeStateDiff(raw: StateDiff | NotAvailable): StateDiff | NotAvailable {
  if (isNotAvailable(raw)) return raw
  return { ...raw, entries: asArray<DiffEntry>(raw.entries) as DiffEntry[] }
}

/**
 * Re-exported from the client, where the single `not_available` narrowing lives.
 * Kept on this module so the page's own imports do not have to change.
 */
export { availableOrNull, isNotAvailable } from '@/api/client'

interface RerunPage {
  readonly reruns: readonly RerunRow[]
}

export type RerunsStatus = 'pending' | 'error' | 'unavailable' | 'ready'

export interface RerunsView {
  readonly status: RerunsStatus
  readonly rows: readonly RerunRow[]
  /** Why there is nothing to show: the error message, or the server's reason. */
  readonly reason: string | null
}

interface RerunsQueryLike {
  readonly isPending: boolean
  readonly isError: boolean
  readonly error: ApiError | null
  readonly data: ApiResult<RerunPage | NotAvailable> | undefined
}

/**
 * One reading of the re-runs query for both consumers. An empty `rows` is only
 * ever "this run has no re-runs" when the status is `ready`; a failure and a
 * `not_available` each keep their own status so neither is drawn as zero.
 */
export function unwrapReruns(query: RerunsQueryLike): RerunsView {
  if (query.isError) {
    return { status: 'error', rows: [], reason: query.error?.message ?? 'The request failed.' }
  }
  if (query.isPending || !query.data) return { status: 'pending', rows: [], reason: null }
  const payload = query.data.data
  if (isNotAvailable(payload)) {
    return { status: 'unavailable', rows: [], reason: payload.reason }
  }
  return { status: 'ready', rows: payload.reruns, reason: null }
}

type Query<T> = UseQueryResult<ApiResult<T>, ApiError>

// Module-level so the selector's identity is stable: an inline arrow makes
// react-query re-run it on every render.
const selectRunDetail = (result: ApiResult<RunDetail>): ApiResult<RunDetail> => ({
  ...result,
  data: normalizeRunDetail(result.data),
})
const selectStepPayload = (result: ApiResult<StepPayload>): ApiResult<StepPayload> => ({
  ...result,
  data: normalizeStepPayload(result.data),
})
const selectStateDiff = (
  result: ApiResult<StateDiff | NotAvailable>,
): ApiResult<StateDiff | NotAvailable> => ({ ...result, data: normalizeStateDiff(result.data) })
const selectReruns = (
  result: ApiResult<RerunPage | NotAvailable>,
): ApiResult<RerunPage | NotAvailable> => ({
  ...result,
  data: isNotAvailable(result.data)
    ? result.data
    : { reruns: asArray<RerunRow>(result.data?.reruns) },
})
const selectRerunSteps = (
  result: ApiResult<readonly StepView[] | NotAvailable>,
): ApiResult<readonly StepView[] | NotAvailable> => ({
  ...result,
  data: isNotAvailable(result.data) ? result.data : asArray<StepView>(result.data),
})

export function useRunDetailQuery(runId: string): Query<RunDetail> {
  return useQuery<ApiResult<RunDetail>, ApiError>({
    queryKey: runDetailKeys.detail(runId),
    queryFn: ({ signal }) => apiFetch<RunDetail>(runDetailPaths.detail(runId), { signal }),
    select: selectRunDetail,
  })
}

export function useStepQuery(runId: string, stepIdx: number | null): Query<StepPayload> {
  return useQuery<ApiResult<StepPayload>, ApiError>({
    queryKey: runDetailKeys.step(runId, stepIdx ?? -1),
    queryFn: ({ signal }) =>
      apiFetch<StepPayload>(runDetailPaths.step(runId, stepIdx ?? -1), { signal }),
    select: selectStepPayload,
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
    select: selectStateDiff,
    enabled: stepIdx !== null,
  })
}

export function useRerunsQuery(runId: string): Query<RerunPage | NotAvailable> {
  return useQuery<ApiResult<RerunPage | NotAvailable>, ApiError>({
    queryKey: runDetailKeys.reruns(runId),
    queryFn: ({ signal }) =>
      apiFetch<RerunPage | NotAvailable>(runDetailPaths.reruns(runId), { signal }),
    select: selectReruns,
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
    select: selectRerunSteps,
  })
}
