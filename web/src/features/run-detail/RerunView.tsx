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

import { type Arm, forkCellState, forkLabel, rerunSummary } from './rerunNarrative'
import { MAX_CELL_WIDTH_PX, MIN_CELL_WIDTH_PX } from './timelineScale'

import {
  type RerunRow,
  type StepView,
  availableOrNull,
  unwrapReruns,
  useRerunStepsQuery,
  useRerunsQuery,
  useRunDetailQuery,
} from './api'

interface RerunViewProps {
  readonly runId: string
  readonly rerunId: string
}

function tapeState(
  step: number,
  forkStep: number,
  last: number,
  passed: boolean,
  arm: Arm,
): TapeStepState {
  if (step < forkStep) return 'tape'
  if (step === forkStep) return forkCellState(arm)
  if (step === last) return passed ? 'passed' : 'failed'
  return 'ran'
}

interface RerunTapeProps {
  readonly nSteps: number
  readonly forkStep: number
  readonly passed: boolean
  readonly arm: Arm
}

/** The same tape, showing where this one re-run forked from the recording. */
function RerunTape({ nSteps, forkStep, passed, arm }: RerunTapeProps) {
  return (
    <div className="[scrollbar-width:none] overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden">
      {/* Cells fill the panel the way the run tape does, rather than sitting as a
          small motif with the rest of the width empty. */}
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${nSteps}, minmax(${MIN_CELL_WIDTH_PX}px, ${MAX_CELL_WIDTH_PX}px))`,
        }}
      >
        {Array.from({ length: nSteps }, (_, index) => index + 1).map((step) => (
          <TapeStep
            key={step}
            step={step}
            state={tapeState(step, forkStep, nSteps, passed, arm)}
            size="fluid"
          />
        ))}
      </div>
    </div>
  )
}

interface StepColumnProps {
  readonly label: string
  readonly steps: readonly StepView[]
  readonly forkStep: number
  readonly changed: ReadonlySet<number>
  readonly arm: Arm
}

/** One side of the recorded-vs-re-run comparison. */
function StepColumn({ label, steps, forkStep, changed, arm }: StepColumnProps) {
  return (
    <div className="min-w-0">
      <InstrumentLabel as="h3" className="mb-2 block">
        {label}
      </InstrumentLabel>
      <ul className="flex flex-col gap-1">
        {steps.map((step) => (
          <StepRow
            key={step.step_idx}
            step={step}
            forkStep={forkStep}
            changed={changed.has(step.step_idx)}
            arm={arm}
          />
        ))}
      </ul>
    </div>
  )
}

/** Steps whose tool or text this re-run produced differently from the recording. */
function changedSteps(
  recorded: readonly StepView[],
  rerun: readonly StepView[],
): ReadonlySet<number> {
  const byIndex = new Map(recorded.map((step) => [step.step_idx, step]))
  const changed = new Set<number>()
  for (const step of rerun) {
    const original = byIndex.get(step.step_idx)
    if (!original) continue
    if (original.text !== step.text || original.tool_name !== step.tool_name) {
      changed.add(step.step_idx)
    }
  }
  return changed
}

interface StepRowProps {
  readonly step: StepView
  readonly forkStep: number
  readonly changed: boolean
  readonly arm: Arm
}

function StepRow({ step, forkStep, changed, arm }: StepRowProps) {
  const isFork = step.step_idx === forkStep
  const forkIntervened = isFork && arm === 'treated'
  return (
    <li
      className={cn(
        'flex min-h-14 items-start gap-3 border-l-2 py-2 pl-3',
        step.from_tape ? 'border-tape bg-tape-tint' : 'border-measure',
        // Amber marks the arm that actually replaced something, never the control.
        forkIntervened
          ? 'border-blame bg-blame-tint'
          : isFork
            ? 'border-measure bg-measure-tint'
            : '',
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
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[11px] text-ink-muted">
          <span>
            {isFork ? forkLabel(arm) : step.from_tape ? 'read from tape · 0 calls' : 're-run live'}
          </span>
          {changed && !isFork ? (
            <span className="text-measure">differs from the recording</span>
          ) : null}
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

  const rerunsView = unwrapReruns(reruns)

  if (steps.isPending || rerunsView.status === 'pending') {
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

  // Without the run's re-run rows there is no arm, seed or fork step to show,
  // and an absent row must not be reported as "no such re-run".
  if (rerunsView.status === 'error') {
    return (
      <ErrorState
        title="This re-run failed to load"
        message={rerunsView.reason ?? 'The request failed.'}
        onRetry={() => void reruns.refetch()}
      />
    )
  }

  const row = rerunsView.rows.find((entry) => entry.rerun_id === rerunId)
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

  const recorded = run.data?.data.steps ?? []
  const nSteps = recorded.length || row.n_steps
  const recordedTail = recorded.filter((step) => step.step_idx >= row.step)
  const changed = changedSteps(recorded, stepList)

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
          <RerunTape nSteps={nSteps} forkStep={row.step} passed={row.passed} arm={row.arm} />
          <p className="mt-3 font-mono text-small text-ink-muted">
            steps 1–{Math.max(row.step - 1, 0)} read from tape · 0 calls · forked at k={row.step} ·{' '}
            {row.calls} calls spent
          </p>
        </div>
        <div className="shrink-0 border-t border-line pt-4 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-6">
          <Meta row={row} />
        </div>
      </Panel>

      {/* Side by side, because the only question this view answers is what this
          arm changed downstream of the fork. */}
      <Panel variant="card" label="from the fork · recorded vs this re-run">
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 lg:grid-cols-2">
          <StepColumn
            label="recorded"
            steps={recordedTail}
            forkStep={row.step}
            changed={changed}
            arm={row.arm}
          />
          <StepColumn
            label="this re-run"
            steps={stepList}
            forkStep={row.step}
            changed={changed}
            arm={row.arm}
          />
        </div>
        <p className="mt-4 border-t border-line pt-3 text-small text-pretty text-ink-muted">
          {rerunSummary(row.arm, row.step, changed.size)}
        </p>
      </Panel>
    </div>
  )
}
