import { ActorGlyph } from '@/components/primitives/ActorGlyph'
import { DiffBlock } from '@/components/primitives/DiffBlock'
import { ErrorState } from '@/components/primitives/ErrorState'
import { JsonView } from '@/components/primitives/JsonView'
import { LoadingRegion, Skeleton } from '@/components/primitives/Skeleton'
import { Tabs } from '@/components/primitives/Tabs'
import { cn } from '@/lib/utils'

import {
  availableOrNull,
  useInterventionDiffQuery,
  useStateDiffQuery,
  useStepQuery,
  type StepView,
} from './api'
import { StateDiffTree } from './StateDiffTree'

interface StepInspectorProps {
  readonly runId: string
  readonly step: StepView | undefined
  readonly stepIdx: number
}

function InspectorSkeleton() {
  return (
    <LoadingRegion subject="the step payload" className="flex flex-col gap-2">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-24 w-full rounded-chart" />
      <Skeleton className="h-24 w-full rounded-chart" />
    </LoadingRegion>
  )
}

function Messages({ messages }: { readonly messages: readonly Record<string, string>[] }) {
  if (messages.length === 0) {
    return <p className="text-small text-ink-muted">This step recorded no messages.</p>
  }
  return (
    <ul className="flex flex-col gap-2">
      {messages.map((message, index) => (
        // Position is the identity of a message in a transcript.
        <li key={index} className="rounded-chart border border-line bg-ground px-3 py-2 text-small">
          <span className="label-instrument">{message.role ?? 'message'}_</span>
          <p className="mt-1 break-words whitespace-pre-wrap text-ink">{message.content ?? ''}</p>
        </li>
      ))}
    </ul>
  )
}

/** Messages, tool call and tool result, the intervention and the DB-state diff for one step. */
export function StepInspector({ runId, step, stepIdx }: StepInspectorProps) {
  const payload = useStepQuery(runId, stepIdx)
  const intervention = useInterventionDiffQuery(runId, stepIdx)
  const stateDiff = useStateDiffQuery(runId, stepIdx)

  if (payload.isPending) return <InspectorSkeleton />
  if (payload.isError) {
    return (
      <ErrorState
        title="This step failed to load"
        message={payload.error.message}
        code={payload.error.code}
        onRetry={() => void payload.refetch()}
      />
    )
  }

  const data = payload.data.data
  const diff = intervention.data ? availableOrNull(intervention.data.data) : null
  const state = stateDiff.data ? availableOrNull(stateDiff.data.data) : null

  const payloadTab = (
    <div className="flex flex-col gap-3">
      <Messages messages={data.messages} />
      {data.tool_args ? <JsonView label="tool args" value={data.tool_args} /> : null}
      {data.tool_result ? <JsonView label="tool result" value={data.tool_result} /> : null}
      {!data.tool_args && !data.tool_result ? (
        <p className="text-small text-ink-muted">
          No tool call at this step; only the {step?.actor ?? 'agent'} turn above.
        </p>
      ) : null}
    </div>
  )

  const interventionTab = intervention.isPending ? (
    <Skeleton className="h-20 w-full rounded-chart" />
  ) : diff ? (
    <div className="flex flex-col gap-3">
      <DiffBlock
        label={`step ${diff.step_idx} · tool result replaced`}
        before={JSON.stringify(diff.original_tool_result)}
        after={JSON.stringify(diff.replaced_tool_result)}
      />
      <div className="grid gap-3 md:grid-cols-2">
        <JsonView label="recorded" value={diff.original_tool_result} />
        <JsonView label="replaced" value={diff.replaced_tool_result} />
      </div>
    </div>
  ) : (
    <p className="text-small text-ink-muted">
      Step {stepIdx} was never intervened on, so there is nothing to diff. Only tested steps have a
      treated arm.
    </p>
  )

  const stateTab = stateDiff.isPending ? (
    <Skeleton className="h-20 w-full rounded-chart" />
  ) : state ? (
    <StateDiffTree entries={state.entries} stepIdx={state.step_idx} />
  ) : (
    <p className="text-small text-ink-muted">
      The database state around this step is not available from this recording.
    </p>
  )

  return (
    <div>
      <p className="mb-3 flex flex-wrap items-center gap-2 text-small">
        {step ? <ActorGlyph actor={step.actor} size="sm" showLabel /> : null}
        {step?.tool_name ? (
          <code className="rounded-step border border-line bg-ground px-1.5 py-0.5 font-mono text-ink">
            {step.tool_name}
          </code>
        ) : null}
        <span className={cn('min-w-0 text-ink-muted', 'break-words')}>{step?.text}</span>
      </p>
      <Tabs
        label="Step inspector"
        items={[
          { value: 'payload', label: 'Payload', content: payloadTab },
          { value: 'intervention', label: 'Intervention', content: interventionTab },
          { value: 'state', label: 'DB state', content: stateTab },
        ]}
      />
    </div>
  )
}
