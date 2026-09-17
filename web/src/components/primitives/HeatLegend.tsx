/**
 * The key to a blame heat stripe. Without it the ramp is a gradient nobody can
 * read: you can see that two steps differ, but not by how much.
 *
 * The scope matters and is stated, because `HeatStripe` builds its ramp from
 * its own run. One stripe (a run page) can print its real range. A column of
 * stripes cannot — each row is scaled to itself, so equal colours on two rows
 * do not mean equal effects, and printing a single range there would be a lie.
 */
import { cn } from '@/lib/utils'

import { SCALE_STEPS, bucketVariable } from './heatScale'

const SWATCH_CLASS = 'h-2.5 w-3 rounded-[2px] border border-line-strong'
const RAMP_BUCKETS = Array.from({ length: SCALE_STEPS }, (_, index) => index + 1)

interface HeatLegendProps {
  /**
   * The ramp's real range, for a view showing exactly one stripe. Omit it when
   * several stripes are on screen: `perRun` says so instead.
   */
  readonly domain?: readonly [number, number] | null
  /** True when every stripe in view has its own domain. */
  readonly perRun?: boolean
  /** Formats an effect the way the rest of the view does. */
  readonly format: (effect: number) => string
  readonly className?: string
}

export function HeatLegend({ domain, perRun = false, format, className }: HeatLegendProps) {
  const range = !perRun && domain ? `${format(domain[0])} … ${format(domain[1])}` : null

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-ink-muted',
        className,
      )}
    >
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="flex gap-px">
          {RAMP_BUCKETS.map((bucket) => (
            <span
              key={bucket}
              className={SWATCH_CLASS}
              style={{ background: bucketVariable(bucket) }}
            />
          ))}
        </span>
        {range ? <span className="num">effect {range}</span> : <span>effect · scaled per run</span>}
      </span>

      <span className="flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className={cn(SWATCH_CLASS, 'border-transparent blame-gradient')}
        />
        blamed
      </span>

      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className={cn(SWATCH_CLASS, 'hatch')} />
        untested
      </span>
    </div>
  )
}
