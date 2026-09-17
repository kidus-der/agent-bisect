import { useCallback } from 'react'

import { useNumberTicker } from '@/design/motion'
import { type NumberFormatOptions, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

import { InstrumentLabel } from './InstrumentLabel'

interface StatTickerProps extends NumberFormatOptions {
  readonly label: string
  readonly value: number
  /** Short line under the number: the unit, the n, or the interval. */
  readonly caption?: string
  readonly size?: 'stat' | 'display'
  readonly className?: string
}

/** KPI number: tabular Geist Mono, springs to its value, announced once at its final value. */
export function StatTicker({
  label,
  value,
  caption,
  size = 'stat',
  decimals,
  prefix,
  suffix,
  signed,
  className,
}: StatTickerProps) {
  const format = useCallback(
    (current: number) => formatNumber(current, { decimals, prefix, suffix, signed }),
    [decimals, prefix, suffix, signed],
  )
  const tickerRef = useNumberTicker<HTMLSpanElement>(value, format)
  return (
    <div data-slot="stat-ticker" className={cn('flex flex-col gap-1', className)}>
      <InstrumentLabel>{label}</InstrumentLabel>
      <span className="sr-only">{format(value)}</span>
      <span
        ref={tickerRef}
        aria-hidden="true"
        className={cn(
          'block num text-ink',
          size === 'display' ? 'text-display font-semibold' : 'text-stat',
        )}
      >
        {format(value)}
      </span>
      {caption ? <span className="text-small text-ink-muted">{caption}</span> : null}
    </div>
  )
}
