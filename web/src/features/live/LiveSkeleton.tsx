import { Panel } from '@/components/primitives/Panel'
import { Skeleton } from '@/components/primitives/Skeleton'

const MODEL_ROWS = [0, 1]
const FEED_ROWS = [0, 1, 2, 3, 4]

/** The Live blueprint in blocks: two model traces, the rail, then queue and feed. */
export function LiveSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1.6fr)]">
        <Panel variant="canvas" bodyClassName="flex flex-col gap-5">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-9 w-2/3 max-w-sm" />
          {MODEL_ROWS.map((row) => (
            <div key={row} className="flex flex-col gap-2">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-36 w-full rounded-chart" />
            </div>
          ))}
        </Panel>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
          <Panel variant="chart">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-4 h-36 w-full rounded-chart" />
          </Panel>
          <Panel variant="chart">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-4 h-36 w-full rounded-chart" />
          </Panel>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel variant="card">
          <Skeleton className="h-3 w-24" />
          {FEED_ROWS.map((row) => (
            <div key={row} className="mt-3 flex items-center gap-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-2 flex-1" />
              <Skeleton className="h-3 w-14" />
            </div>
          ))}
        </Panel>
        <Panel variant="card">
          <Skeleton className="h-3 w-24" />
          {FEED_ROWS.map((row) => (
            <div key={row} className="mt-3 flex items-center gap-3">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-10" />
              <Skeleton className="h-3 flex-1" />
            </div>
          ))}
        </Panel>
      </div>
    </div>
  )
}
