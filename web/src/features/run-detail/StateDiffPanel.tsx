import { memo } from 'react'

import { ErrorState } from '@/components/primitives/ErrorState'
import { Skeleton } from '@/components/primitives/Skeleton'

import { availableOrNull, useStateDiffQuery } from './api'
import { StateDiffTree } from './StateDiffTree'

interface StateDiffPanelProps {
  readonly runId: string
  readonly stepIdx: number
}

/**
 * What the selected step did to the world. It sits beside the re-run matrix
 * rather than inside the inspector's tabs: both answer "what happened at this
 * step", and together they fill a row that either alone leaves half empty.
 */
function StateDiffPanelImpl({ runId, stepIdx }: StateDiffPanelProps) {
  const stateDiff = useStateDiffQuery(runId, stepIdx)

  if (stateDiff.isPending) return <Skeleton className="h-20 w-full rounded-chart" />
  if (stateDiff.isError) {
    return (
      <ErrorState
        title="The database state diff failed to load"
        message={stateDiff.error.message}
        code={stateDiff.error.code}
        onRetry={() => void stateDiff.refetch()}
      />
    )
  }

  const state = availableOrNull(stateDiff.data.data)
  if (!state) {
    return (
      <p className="text-small text-ink-muted">
        The database state around this step is not available from this recording.
      </p>
    )
  }
  return <StateDiffTree entries={state.entries} stepIdx={state.step_idx} />
}

export const StateDiffPanel = memo(StateDiffPanelImpl)
