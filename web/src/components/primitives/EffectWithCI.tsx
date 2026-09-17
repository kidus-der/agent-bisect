import { useId } from 'react'

import { formatEffect, formatInterval } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface EffectEstimate {
  readonly estimate: number
  readonly low: number
  readonly high: number
}

interface EffectWithCIProps extends EffectEstimate {
  /** Decision threshold drawn as a dashed line. */
  readonly delta?: number
  readonly domain?: readonly [min: number, max: number]
  readonly variant?: 'text' | 'bar' | 'both'
  /** Blamed estimates take the blame colour; everything else is measurement cyan. */
  readonly blamed?: boolean
  readonly className?: string
}

const BAR_WIDTH = 168
const BAR_HEIGHT = 18
const BAR_MID = BAR_HEIGHT / 2
const POINT_SIZE = 8
const CAP_HALF = 4
const DEFAULT_DOMAIN = [-1, 1] as const

function scaleTo(domain: readonly [number, number]): (value: number) => number {
  const [min, max] = domain
  const span = max - min || 1
  return (value) => ((Math.min(max, Math.max(min, value)) - min) / span) * BAR_WIDTH
}

interface IntervalBarProps extends EffectEstimate {
  readonly delta?: number
  readonly domain: readonly [number, number]
  readonly blamed: boolean
}

function IntervalBar({ estimate, low, high, delta, domain, blamed }: IntervalBarProps) {
  const gradientId = useId()
  const x = scaleTo(domain)
  const stroke = blamed ? `url(#${gradientId})` : 'var(--bx-measure)'
  return (
    <svg
      aria-hidden="true"
      width={BAR_WIDTH}
      height={BAR_HEIGHT}
      viewBox={`0 0 ${BAR_WIDTH} ${BAR_HEIGHT}`}
      className="shrink-0 overflow-visible"
    >
      <defs>
        <linearGradient id={gradientId} gradientUnits="userSpaceOnUse" x1={x(low)} x2={x(high)}>
          <stop offset="0" stopColor="var(--bx-blame)" />
          <stop offset="1" stopColor="var(--bx-blame-coral)" />
        </linearGradient>
      </defs>
      <line x1={0} x2={BAR_WIDTH} y1={BAR_MID} y2={BAR_MID} stroke="var(--bx-line)" />
      <line x1={x(0)} x2={x(0)} y1={0} y2={BAR_HEIGHT} stroke="var(--bx-muted)" />
      {delta === undefined ? null : (
        <line
          x1={x(delta)}
          x2={x(delta)}
          y1={0}
          y2={BAR_HEIGHT}
          stroke="var(--bx-muted)"
          strokeDasharray="2 2"
        />
      )}
      <line x1={x(low)} x2={x(high)} y1={BAR_MID} y2={BAR_MID} stroke={stroke} strokeWidth={2} />
      {[low, high].map((bound) => (
        <line
          key={bound}
          x1={x(bound)}
          x2={x(bound)}
          y1={BAR_MID - CAP_HALF}
          y2={BAR_MID + CAP_HALF}
          stroke={stroke}
          strokeWidth={2}
        />
      ))}
      <rect
        x={x(estimate) - POINT_SIZE / 2}
        y={BAR_MID - POINT_SIZE / 2}
        width={POINT_SIZE}
        height={POINT_SIZE}
        rx={1}
        fill={blamed ? 'var(--bx-blame)' : 'var(--bx-measure)'}
        stroke="var(--bx-surface)"
      />
    </svg>
  )
}

/** An estimate never appears without its interval. */
export function EffectWithCI({
  estimate,
  low,
  high,
  delta,
  domain = DEFAULT_DOMAIN,
  variant = 'both',
  blamed = false,
  className,
}: EffectWithCIProps) {
  return (
    <span data-slot="effect-with-ci" className={cn('inline-flex items-center gap-3', className)}>
      {variant === 'text' ? null : (
        <IntervalBar
          estimate={estimate}
          low={low}
          high={high}
          delta={delta}
          domain={domain}
          blamed={blamed}
        />
      )}
      <span className={cn('num text-small whitespace-nowrap', variant === 'bar' && 'sr-only')}>
        <span className="sr-only">effect </span>
        <span className={cn('font-semibold', blamed ? 'text-blame' : 'text-ink')}>
          {formatEffect(estimate)}
        </span>{' '}
        <span className="text-ink-muted">
          <span className="sr-only">95% confidence interval </span>
          {formatInterval(low, high)}
        </span>
      </span>
    </span>
  )
}
