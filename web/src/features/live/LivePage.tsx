import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { NotMeasuredState } from '@/components/primitives/NotMeasuredState'
import { Panel } from '@/components/primitives/Panel'
import { LoadingRegion } from '@/components/primitives/Skeleton'
import { splitNotAvailable } from '@/api/payload'
import { PageHeader } from '@/pages/PageHeader'

import type { LiveSnapshot } from './api'
import { useLiveSnapshotQuery } from './api'
import { BudgetGauge } from './BudgetGauge'
import { CallsPerModel } from './CallsPerModel'
import { EventFeed } from './EventFeed'
import { HeadroomRing } from './HeadroomRing'
import { JobQueue } from './JobQueue'
import { LiveSkeleton } from './LiveSkeleton'
import { LiveStatus } from './LiveStatus'
import { mergeEvents } from './liveBuffer'
import { useLiveStream } from './useLiveStream'
import { useNow } from './useNow'

export const BLAME_COMMAND = 'bisect blame RUN_ID --top 3 --n 8'
/** Coarse: the ages printed are to the second, and a finer tick buys nothing. */
const CLOCK_TICK_MS = 5000

function isIdle(snapshot: LiveSnapshot): boolean {
  return (
    snapshot.jobs.length === 0 && snapshot.events.length === 0 && snapshot.calls_series.length === 0
  )
}

interface LiveBodyProps {
  readonly snapshot: LiveSnapshot
  readonly events: readonly LiveSnapshot['events'][number][]
  readonly simulated: boolean
  readonly status: React.ReactNode
  readonly now: number
}

function LiveBody({ snapshot, events, simulated, status, now }: LiveBodyProps) {
  if (isIdle(snapshot)) {
    return (
      <Panel variant="canvas">
        <EmptyState
          label="no jobs in flight"
          title="Nothing is running"
          description="Live shows replay jobs while they execute. Start a blame job and its calls appear here as they happen."
          command={BLAME_COMMAND}
        />
      </Panel>
    )
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1.6fr)]">
        <CallsPerModel rows={snapshot.calls_series} simulated={simulated} status={status} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
          <BudgetGauge budget={snapshot.budget} />
          <HeadroomRing rateLimit={snapshot.rate_limit} />
        </div>
      </div>
      <JobQueue jobs={snapshot.jobs} />
      <EventFeed events={events} now={now} />
    </div>
  )
}

export function LivePage() {
  const initial = useLiveSnapshotQuery()
  const stream = useLiveStream()
  const now = useNow(CLOCK_TICK_MS)

  const initialSplit = initial.data ? splitNotAvailable<LiveSnapshot>(initial.data.data) : null
  const snapshot = stream.snapshot ?? initialSplit?.payload ?? null
  const reason = stream.snapshot ? stream.notAvailableReason : (initialSplit?.reason ?? null)
  const simulated = stream.meta?.simulated ?? initial.data?.meta.simulated ?? false

  // The stream's ring is authoritative once it has frames; before that, the
  // first snapshot's own events stand in so the feed is never empty on arrival.
  const events = stream.events.length > 0 ? stream.events : mergeEvents([], snapshot?.events ?? [])

  return (
    <>
      <PageHeader
        label="live"
        title="Live"
        description="Jobs in flight, the call budget and rate-limit headroom, as the server streams them."
      />
      {snapshot === null && reason !== null ? (
        <Panel variant="canvas">
          <NotMeasuredState
            label="live"
            title="The server is not tracking calls yet"
            reason={reason}
            command={BLAME_COMMAND}
          />
        </Panel>
      ) : snapshot === null && initial.isError ? (
        <Panel variant="card">
          <ErrorState
            title="Cannot reach the Bisect server"
            message={initial.error.message}
            code={initial.error.code}
            onRetry={() => {
              void initial.refetch()
              stream.retryNow()
            }}
          />
        </Panel>
      ) : snapshot === null ? (
        <LoadingRegion subject="live activity">
          <LiveSkeleton />
        </LoadingRegion>
      ) : (
        <LiveBody
          snapshot={snapshot}
          events={events}
          simulated={simulated}
          now={now}
          status={
            <LiveStatus
              connection={stream.connection}
              updates={stream.updates}
              lastFrameAt={stream.lastFrameAt}
              now={now}
              onRetry={stream.retryNow}
            />
          }
        />
      )}
    </>
  )
}
