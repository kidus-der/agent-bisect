import { Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'

import { ActorGlyph } from '@/components/primitives/ActorGlyph'
import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { LoadingRegion, Skeleton } from '@/components/primitives/Skeleton'
import { TapeStep, type TapeStepState } from '@/components/primitives/TapeStep'
import { cn } from '@/lib/utils'

import {
  type RerunRow,
  type StepView,
  availableOrNull,
  useRerunStepsQuery,
  useRerunsQuery,
  useRunDetailQuery,
} from './api'

interface RerunViewProps {
  readonly runId: string
  readonly rerunId: string
}

function tapeState(step: number, forkStep: number, last: number, passed: boolean): TapeStepState {
  if (step < forkStep) return 'tape'
  if (step === forkStep) return 'blamed'
  if (step === last) return passed ? 'passed' : 'failed'
  return 'ran'
}

interface RerunTapeProps {
  readonly nSteps: number
  readonly forkStep: number
  readonly passed: boolean
}

/** The same tape, showing where this one re-run forked from the recording. */
function RerunTape({ nSteps, forkStep, passed }: RerunTapeProps) {
  return (
    <div className="overflow-x-auto pb-1">
      <div className="flex gap-1">
        {Array.from({ length: nSteps }, (_, index) => index + 1).map((step) => (
          <TapeStep
            key={step}
            step={step}
            state={tapeState(step, forkStep, nSteps, passed)}
            size="sm"
          />
        ))}
      </div>
    </div>
  )
}

function StepRow({ step, forkStep }: { readonly step: StepView; readonly forkStep: number }) {
  const isFork = step.step_idx === forkStep
  return (
    <li
      className={cn(
        'flex items-start gap-3 border-l-2 py-2 pl-3',
        step.from_tape ? 'border-tape bg-tape-tint' : 'border-measure',
        isFork && 'border-blame bg-blame-tint',
      )}
    >
      <span className="w-8 shrink-0 num text-small text-ink-muted">{step.step_idx}</span>
      <ActorGlyph actor={step.actor} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-small">
          {step.tool_name ? (
            <code className="rounded-step border border-line bg-ground px-1.5 font-mono text-ink">
              {step.tool_name}
            </code>
          ) : null}
          <span className="min-w-0 break-words text-ink">{step.text}</span>
        </p>
        <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
          {isFork
            ? 'fork · intervention applied here'
            : step.from_tape
              ? 'read from tape · 0 calls'
              : 're-run live'}
        </p>
      </div>
    </li>
  )
}

function Meta({ row }: { readonly row: RerunRow }) {
  const facts = [
    ['arm', row.arm],
    ['fork step', `k=${row.step}`],
    ['seed', String(row.seed)],
    ['calls', String(row.calls)],
  ] as const
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-2">
      {facts.map(([label, value]) => (
        <div key={label} className="flex flex-col gap-0.5">
          <dt>
            <InstrumentLabel>{label}</InstrumentLabel>
          </dt>
          <dd className="num text-small text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** One individual re-run: where it forked, what it read from tape, how it ended. */
export function RerunView({ runId, rerunId }: RerunViewProps) {
  const run = useRunDetailQuery(runId)
  const reruns = useRerunsQuery(runId)
  const steps = useRerunStepsQuery(runId, rerunId)

  const backLink = (
    <Link
      to="/runs/$runId"
      params={{ runId }}
      className="inline-flex items-center gap-1.5 text-small text-ink-muted hover:text-ink"
    >
      <ArrowLeft aria-hidden="true" className="size-3.5" />
      {runId}
    </Link>
  )

  if (steps.isPending || reruns.isPending) {
    return (
      <LoadingRegion subject="this re-run" className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-16 w-full rounded-card" />
        <Skeleton className="h-64 w-full rounded-card" />
      </LoadingRegion>
    )
  }

  if (steps.isError) {
    return (
      <ErrorState
        title="This re-run failed to load"
        message={steps.error.message}
        code={steps.error.code}
        onRetry={() => void steps.refetch()}
      />
    )
  }

  const rows = availableOrNull(reruns.data?.data ?? null)?.reruns ?? []
  const row = rows.find((entry) => entry.rerun_id === rerunId)
  const stepList = availableOrNull(steps.data.data) ?? []

  if (!row || stepList.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        {backLink}
        <EmptyState
          label="re-run not found"
          title={`No re-run ${rerunId} in this run`}
          description="Individual re-runs only exist for steps the estimator actually tested. Open the run and pick a dot from the treated-vs-control matrix."
        />
      </div>
    )
  }

  const nSteps = run.data?.data.steps.length ?? row.n_steps

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {backLink}
        <PassFailPill outcome={row.passed ? 'pass' : 'fail'} />
      </div>
      <h1 className="font-mono text-h2 text-ink">{rerunId}</h1>

      <Panel
        variant="canvas"
        label="tape · this re-run"
        bodyClassName="flex flex-col gap-6 xl:flex-row xl:items-start xl:gap-8"
      >
        <div className="min-w-0 flex-1">
          <RerunTape nSteps={nSteps} forkStep={row.step} passed={row.passed} />
          <p className="mt-3 font-mono text-small text-ink-muted">
            steps 1–{Math.max(row.step - 1, 0)} read from tape · 0 calls · forked at k={row.step} ·{' '}
            {row.calls} calls spent
          </p>
        </div>
        <div className="shrink-0 border-t border-line pt-4 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-6">
          <Meta row={row} />
        </div>
      </Panel>

      <Panel variant="card" label="steps from the fork" bodyClassName="flex flex-col gap-1">
        <ul className="flex flex-col gap-1">
          {stepList.map((step) => (
            <StepRow key={step.step_idx} step={step} forkStep={row.step} />
          ))}
        </ul>
      </Panel>
    </div>
  )
}
