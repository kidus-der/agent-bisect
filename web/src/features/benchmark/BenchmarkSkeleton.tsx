import { Panel } from '@/components/primitives/Panel'
import { Skeleton, TableSkeleton } from '@/components/primitives/Skeleton'

const METHOD_ROWS = [0, 1, 2, 3, 4]
const BAR_WIDTHS = ['w-[92%]', 'w-[78%]', 'w-[68%]', 'w-[88%]', 'w-[70%]'] as const

/** The Benchmark blueprint in blocks: the comparison first, at its real proportions. */
export function BenchmarkSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Panel variant="canvas" bodyClassName="flex flex-col gap-5">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-7 w-2/3 max-w-md" />
        <div className="flex flex-wrap gap-8 rounded-card border border-line bg-surface p-4">
          <Skeleton className="h-11 w-28" />
          <Skeleton className="h-11 w-24" />
          <Skeleton className="h-11 w-36" />
        </div>
        <div className="flex flex-col gap-3">
          {METHOD_ROWS.map((row) => (
            <div key={row} className="flex items-center gap-4">
              <Skeleton className="h-4 w-32 shrink-0" />
              <Skeleton className={`h-4 ${BAR_WIDTHS[row]}`} />
              <Skeleton className="h-4 w-14 shrink-0" />
            </div>
          ))}
        </div>
      </Panel>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        <Panel variant="chart">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="mt-4 h-56 w-full rounded-chart" />
        </Panel>
        <Panel variant="chart">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="mt-4 h-56 w-full rounded-chart" />
        </Panel>
      </div>
      <Panel variant="chart">
        <Skeleton className="h-3 w-36" />
        <Skeleton className="mt-4 h-64 w-full rounded-chart" />
      </Panel>
      <Panel variant="card">
        <TableSkeleton rows={6} />
      </Panel>
    </div>
  )
}
