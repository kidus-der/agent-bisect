import { cn } from '@/lib/utils'

import { ZERO_MIDPOINT_PERCENT, deltaBarGeometry } from './deltaBarGeometry'

/** Anything below this is a real regression rather than floating-point dust. */
export const WORSE_THRESHOLD = -0.0001

/**
 * One width for the bars and for the key above them. They are not stacked in the
 * same column, so the key has to be recognisable as a key rather than an axis —
 * sharing the track width is what lets a reader match the two by eye.
 */
export const TRACK_WIDTH = 'w-40'

/**
 * Zero, drawn at the one x the bars anchor on. It overhangs its row so the
 * rules in consecutive rows join into a single line down the column — a bar's
 * side only means something against a zero the reader can see.
 */
export function ZeroRule({ overhang = true }: { readonly overhang?: boolean }) {
  return (
    <span
      className={cn('absolute z-10 w-px bg-line-strong', overhang ? '-inset-y-3' : 'inset-y-0')}
      style={{ left: `${ZERO_MIDPOINT_PERCENT}%` }}
    />
  )
}

/**
 * A bar either side of a centre zero line, scaled against the largest change in
 * the suite — so the longest bar is the worst scenario and every other bar is
 * readable against it. Scaled against the full 0-100 range instead, every row
 * drew the same stub and the mark encoded nothing.
 */
export function DeltaBar({ value, scale }: { readonly value: number; readonly scale: number }) {
  const worse = value < WORSE_THRESHOLD
  const bar = deltaBarGeometry(value, scale)
  return (
    <span aria-hidden="true" className={cn('relative inline-block h-4 align-middle', TRACK_WIDTH)}>
      {/* Anchored on the axis midpoint the header declares: the side says the
          sign, the length says the size. */}
      <span
        className={cn(
          'absolute top-1/2 h-2.5 -translate-y-1/2',
          worse ? 'rounded-l-step bg-fail' : 'rounded-r-step bg-pass',
        )}
        style={{ left: `${bar.left}%`, width: `${bar.width}%` }}
      />
      <ZeroRule />
    </span>
  )
}
