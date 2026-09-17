/** Each page's §5 blueprint drawn in skeleton blocks, so loading already has the final layout. */
import { Panel } from '@/components/primitives/Panel'
import { Skeleton, TableSkeleton } from '@/components/primitives/Skeleton'

const KPI_KEYS = ['n', 'delta', 'cost'] as const
const TAPE_KEYS = Array.from({ length: 12 }, (_, index) => index)

function KpiRow() {
  return (
    <div className="grid grid-cols-3 gap-3">
      {KPI_KEYS.map((key) => (
        <Panel key={key} variant="kpi">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="mt-3 h-8 w-20" />
        </Panel>
      ))}
    </div>
  )
}

function ChartBlock({ className }: { readonly className?: string }) {
  return (
    <Panel variant="chart" className={className}>
      <Skeleton className="h-3 w-28" />
      <Skeleton className="mt-4 h-48 w-full rounded-chart" />
    </Panel>
  )
}

export function OverviewSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        <Panel variant="canvas">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="mt-5 h-7 w-4/5" />
          <Skeleton className="mt-3 h-7 w-1/2" />
        </Panel>
        <KpiRow />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartBlock />
        <ChartBlock />
      </div>
      <Panel variant="card">
        <TableSkeleton rows={3} />
      </Panel>
    </div>
  )
}

export function TableSkeletonPage() {
  return (
    <Panel variant="card">
      <TableSkeleton rows={8} />
    </Panel>
  )
}

export function RunDetailSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Panel variant="canvas">
        <Skeleton className="h-3 w-12" />
        <div className="mt-4 grid grid-cols-12 gap-1">
          {TAPE_KEYS.map((key) => (
            <Skeleton key={key} className="h-10 sm:h-12" />
          ))}
        </div>
        <Skeleton className="mt-3 h-4 w-full" />
      </Panel>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartBlock />
        <ChartBlock />
      </div>
    </div>
  )
}

export function BenchmarkSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <ChartBlock className="lg:col-span-2" />
      <div className="flex flex-col gap-4">
        <ChartBlock />
      </div>
    </div>
  )
}

export function LiveSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        <ChartBlock />
        <KpiRow />
      </div>
      <Panel variant="card">
        <TableSkeleton rows={4} />
      </Panel>
    </div>
  )
}

export function PrChecksSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto_1fr]">
      <ChartBlock />
      <div className="flex flex-row justify-center gap-2 md:flex-col">
        <Skeleton className="h-6 w-16 rounded-pill" />
        <Skeleton className="h-6 w-16 rounded-pill" />
      </div>
      <ChartBlock />
    </div>
  )
}
