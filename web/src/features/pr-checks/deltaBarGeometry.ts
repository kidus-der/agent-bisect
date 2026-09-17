/**
 * Where a change bar sits on a symmetric axis whose midpoint is zero.
 *
 * The header declares `−N pts —|— +N pts`; the marks have to obey it. Anchoring
 * every bar on the midpoint means a bar's *side* says the sign and its *length*
 * says the size — which is the only reading that makes the axis legend true.
 */
export interface DeltaBarGeometry {
  /** Left edge, as a percentage of the track. */
  readonly left: number
  /** Width, as a percentage of the track. */
  readonly width: number
}

const PERCENT = 100

/**
 * Where zero sits on the track, as a percentage of its width. The bars, the rule
 * drawn down the column and the key above it all read this one number, so the
 * three cannot drift apart.
 */
export const ZERO_MIDPOINT_PERCENT = 50
const MIDPOINT = ZERO_MIDPOINT_PERCENT

export function deltaBarGeometry(value: number, scale: number): DeltaBarGeometry {
  if (!Number.isFinite(value) || scale <= 0) return { left: MIDPOINT, width: 0 }
  const fraction = Math.min(1, Math.abs(value) / scale)
  const half = (fraction * PERCENT) / 2
  if (value < 0) return { left: MIDPOINT - half, width: half }
  return { left: MIDPOINT, width: half }
}

/**
 * The key above the change column: how far a full-length bar reaches, either
 * way from the rule. `formatPoints` already carries the unit, so the label must
 * not add a second one.
 */
export function scaleKeyLabel(scale: number, formatPoints: (value: number) => string): string {
  return `\u00B1${formatPoints(scale).replace(/^[+\u2212-]/, '')}`
}
