import { formatEffect, formatInterval } from '@/lib/format'
import { cn } from '@/lib/utils'

interface BlameBadgeProps {
  /** 1-based step index that was blamed. */
  readonly step: number
  /** Causal effect estimate. Blame is never shown without it. */
  readonly effect: number
  readonly interval?: readonly [low: number, high: number]
  readonly size?: 'sm' | 'md'
  readonly className?: string
}

/**
 * The signature. The amber->coral gradient is a fill (the ring and the marker);
 * the number sits on a solid amber chip so it is never read against the gradient.
 */
export function BlameBadge({ step, effect, interval, size = 'md', className }: BlameBadgeProps) {
  const compact = size === 'sm'
  return (
    <span
      data-slot="blame-badge"
      className={cn('inline-flex rounded-pill blame-gradient p-px align-middle', className)}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-pill bg-surface pl-2',
          compact ? 'h-5 pr-0.5 text-[11px]' : 'h-6 pr-0.5 text-small',
        )}
      >
        <span aria-hidden="true" className="size-1.5 rounded-full blame-gradient" />
        <span className="font-mono font-medium tracking-wide text-blame uppercase">
          <span className="sr-only">Blame: </span>step {step}
        </span>
        <span
          className={cn(
            'inline-flex items-center rounded-pill bg-blame px-1.5 num font-semibold text-on-role',
            compact ? 'h-4' : 'h-5',
          )}
        >
          <span className="sr-only">effect </span>
          {formatEffect(effect)}
        </span>
        {interval ? (
          <span className="pr-1.5 num text-ink-muted">
            <span className="sr-only">95% confidence interval </span>
            {formatInterval(interval[0], interval[1])}
          </span>
        ) : null}
      </span>
    </span>
  )
}
