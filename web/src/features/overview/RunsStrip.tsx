/**
 * A short strip of runs at the foot of the Overview, as a way into the full
 * list. `/api/runs` cannot sort by time, so these are the longest runs rather
 * than the most recent — and the label says which.
 */
import { Link } from '@tanstack/react-router'
import { ArrowRight } from 'lucide-react'

import { availableOrNull } from '@/api/client'
import { HeatLegend } from '@/components/primitives/HeatLegend'
import { Panel } from '@/components/primitives/Panel'
import { Skeleton } from '@/components/primitives/Skeleton'
import { RunBlame, RunBlameStripe, RunOutcome } from '@/features/runs/cells'
import { useRunSampleQuery } from '@/features/runs/api'
import { formatEffect } from '@/lib/format'

const STRIP_LIMIT = 5
/** One shared stripe width, so blame position is comparable down the column. */
const STRIPE_TARGET_PX = 232

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
        <>
          <ul className="flex flex-col divide-y divide-line">
            {runs.map((run) => (
              <li key={run.run_id}>
                <Link
                  to="/runs/$runId"
                  params={{ runId: run.run_id }}
                  // Fixed tracks, not `auto`: each row is its own grid, so an
                  // `auto` column would resolve to a different width per row and
                  // the stripes would no longer share one step-1 origin.
                  className="grid grid-cols-[11rem_minmax(0,1fr)] items-center gap-x-6 gap-y-1.5 rounded-step py-2.5 hover:text-ink sm:grid-cols-[11rem_minmax(0,1fr)_15rem_9.5rem_5rem]"
                >
                  {/* The id never truncates: at 390 the task gives way instead. */}
                  <span className="num font-medium whitespace-nowrap text-ink">{run.run_id}</span>
                  <span className="min-w-0 truncate text-small text-ink-muted">{run.task_id}</span>
                  {/* Fixed column, left-aligned: step 1 sits at the same x on every row. */}
                  <span className="col-span-2 flex justify-start sm:col-span-1">
                    <RunBlameStripe run={run} targetPx={STRIPE_TARGET_PX} />
                  </span>
                  <span className="justify-self-start">
                    <RunBlame run={run} />
                  </span>
                  <span className="justify-self-start sm:justify-self-end">
                    <RunOutcome run={run} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {/* One key for the column: each row is scaled to its own run. */}
          <HeatLegend perRun format={formatEffect} className="mt-3" />
        </>
      )}
    </Panel>
  )
}
