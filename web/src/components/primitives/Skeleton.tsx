import { cn } from '@/lib/utils'

interface SkeletonProps {
  readonly className?: string
}

/** Placeholder block. The sweep is CSS and stops under prefers-reduced-motion. */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <span aria-hidden="true" className={cn('skeleton-shimmer block rounded-step', className)} />
  )
}

interface LoadingRegionProps {
  /** What is loading: "runs", "benchmark results". */
  readonly subject: string
  readonly children: React.ReactNode
  readonly className?: string
}

/** Wraps skeletons so assistive tech hears one "Loading runs" instead of nothing. */
export function LoadingRegion({ subject, children, className }: LoadingRegionProps) {
  return (
    <div role="status" aria-busy="true" className={className}>
      <span className="sr-only">Loading {subject}</span>
      {children}
    </div>
  )
}

const TABLE_SKELETON_WIDTHS = ['w-16', 'w-32', 'w-24', 'w-28', 'w-14', 'w-12'] as const

interface TableSkeletonProps {
  readonly rows?: number
}

export function TableSkeleton({ rows = 6 }: TableSkeletonProps) {
  return (
    <div className="flex flex-col divide-y divide-line">
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex h-11 items-center gap-6">
          {TABLE_SKELETON_WIDTHS.map((width, column) => (
            <Skeleton key={width} className={cn('h-3', width, column > 2 && 'hidden sm:block')} />
          ))}
        </div>
      ))}
    </div>
  )
}
