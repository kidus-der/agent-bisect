/**
 * The looping rewind, playing the run `/api/overview` nominates as its hero.
 * The run's effect estimate and intervention diff come from the run-detail
 * endpoints, under the same query keys that page uses, so opening the run from
 * here is already warm.
 */
import { availableOrNull } from '@/api/client'
import { RewindLoop } from '@/components/rewind/RewindLoop'
import { Skeleton } from '@/components/primitives/Skeleton'
import { Panel } from '@/components/primitives/Panel'
import { useInterventionDiffQuery, useRunDetailQuery } from '@/features/run-detail/api'

import type { RunSummary } from './api'
import { heroRewindSpec } from './heroRun'

const TAPE_PLACEHOLDER_CELLS = 12

interface HeroRewindProps {
  readonly run: RunSummary
}

function TapePlaceholder() {
  return (
    <Panel variant="canvas" label="rewind">
      <div className="grid grid-cols-12 gap-1">
        {Array.from({ length: TAPE_PLACEHOLDER_CELLS }, (_, index) => (
          <Skeleton key={index} className="h-10 sm:h-12" />
        ))}
      </div>
      <Skeleton className="mt-4 h-4 w-2/3" />
    </Panel>
  )
}

export function HeroRewind({ run }: HeroRewindProps) {
  const detail = useRunDetailQuery(run.run_id)
  const step = run.decisive_step
  const diff = useInterventionDiffQuery(run.run_id, step)

  // The tape needs the step count only; the estimate and diff enrich it when they land.
  if (detail.isPending) return <TapePlaceholder />

  const estimate = detail.data ? (detail.data.data.estimate ?? null) : null
  const spec = heroRewindSpec({
    run,
    estimate,
    interventionDiff: availableOrNull(diff.data?.data ?? null),
  })
  if (!spec) return null

  return (
    <RewindLoop
      spec={spec}
      label={`rewind · ${run.run_id}`}
      runLabel={`Run ${run.run_id}, ${run.domain} · ${run.task_id}`}
      href={`/runs/${run.run_id}`}
    />
  )
}
