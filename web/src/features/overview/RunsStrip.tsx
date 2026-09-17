/**
 * A short strip of runs at the foot of the Overview, as a way into the full
 * list. `/api/runs` cannot sort by time, so these are the longest runs rather
 * than the most recent — and the label says which.
 */
import { Link } from '@tanstack/react-router'
import { ArrowRight } from 'lucide-react'

import { availableOrNull } from '@/api/client'
import { Panel } from '@/components/primitives/Panel'
import { Skeleton } from '@/components/primitives/Skeleton'
import { RunBlame, RunBlameStripe, RunOutcome } from '@/features/runs/cells'
import { useRunSampleQuery } from '@/features/runs/api'

const STRIP_LIMIT = 5

function StripSkeleton() {
  return (
    <ul className="flex flex-col divide-y divide-line">
      {Array.from({ length: STRIP_LIMIT }, (_, index) => (
        <li key={index} className="flex h-12 items-center gap-4">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-3 w-24" />
        </li>
      ))}
    </ul>
  )
}

export function RunsStrip() {
  const query = useRunSampleQuery(STRIP_LIMIT)
  const runs = availableOrNull(query.data?.data ?? null)?.runs ?? []

  return (
    <Panel
      variant="card"
      label="runs · longest first"
      title="Recorded runs"
      actions={
        <Link
          to="/runs"
          className="inline-flex h-8 items-center gap-1 rounded-control border border-line-strong bg-elevated px-2.5 text-small font-medium text-ink hover:border-ink-muted"
        >
          View all
          <ArrowRight aria-hidden="true" className="size-3.5" />
        </Link>
      }
    >
      {query.isPending ? (
        <StripSkeleton />
      ) : runs.length === 0 ? (
        <p className="text-small text-ink-muted">No runs recorded yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line">
          {runs.map((run) => (
            <li key={run.run_id}>
              <Link
                to="/runs/$runId"
                params={{ runId: run.run_id }}
                className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-step py-2.5 hover:text-ink"
              >
                <span className="min-w-0 flex-1 truncate num font-medium text-ink">
                  {run.run_id}
                </span>
                <span className="hidden truncate text-small text-ink-muted sm:block sm:flex-1">
                  {run.task_id}
                </span>
                <RunBlameStripe run={run} />
                <RunBlame run={run} />
                <RunOutcome run={run} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
