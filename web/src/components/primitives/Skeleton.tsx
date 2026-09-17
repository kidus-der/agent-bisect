import { MAX_ATTEMPTS } from '@/api/queries'
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
  /** TanStack Query's `failureCount`: how many attempts have already failed. */
  readonly failureCount?: number
  /** Why the last attempt failed, shown next to the retry count. */
  readonly failureMessage?: string
}

/**
 * Wraps skeletons so assistive tech hears one "Loading runs" instead of nothing.
 * After a failed attempt it says so: a dead server must not look like a slow one.
 */
export function LoadingRegion({
  subject,
  children,
  className,
  failureCount = 0,
  failureMessage,
}: LoadingRegionProps) {
  const retrying = failureCount > 0
  return (
    <div role="status" aria-busy="true" className={className}>
      <span className="sr-only">Loading {subject}</span>
      {retrying ? (
        <p data-slot="retry-notice" className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="label-instrument text-ink">
            retrying… ({Math.min(failureCount + 1, MAX_ATTEMPTS)} of {MAX_ATTEMPTS})
          </span>
          {failureMessage ? (
            <span className="text-small text-ink-muted">{failureMessage}</span>
          ) : null}
        </p>
      ) : null}
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
