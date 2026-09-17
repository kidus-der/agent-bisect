/**
 * Direct labels only beat a legend if they are readable. On a scatter the
 * points are spread in two dimensions, so a label sits beside its point rather
 * than above it: that way two points sharing an x value (two methods costing
 * the same) still get labels that cannot overprint each other.
 */
export interface LabelAnchor {
  readonly id: string
  readonly x: number
  readonly y: number
  /** Characters in the label, used to guess whether it fits to the right. */
  readonly length: number
}

export type LabelSide = 'start' | 'end'

export interface PlacedLabel {
  readonly id: string
  /** Offset from the point, in px. */
  readonly dx: number
  readonly dy: number
  /** SVG `text-anchor` for this side. */
  readonly anchor: LabelSide
}

const GAP_PX = 10
/** Enough to clear the largest marker plus its whisker caps. */
const MARKER_CLEARANCE_PX = 8
const BASELINE_NUDGE_PX = 4
const APPROX_CHAR_PX = 6.6
/** Two labels on the same side within this vertical distance would collide. */
const ROW_HEIGHT_PX = 18

interface Placed {
  readonly left: number
  readonly right: number
  readonly y: number
}

function estimatedWidth(length: number): number {
  return length * APPROX_CHAR_PX
}

/** The horizontal span a label occupies once it is anchored on `side`. */
function span(x: number, side: LabelSide, width: number, offset: number): [number, number] {
  return side === 'start' ? [x + offset, x + offset + width] : [x - offset - width, x - offset]
}

/**
 * Two labels clash when their spans overlap on roughly the same line. Sides are
 * not enough: a right-anchored label reaches back across a left-anchored one.
 */
function collides(left: number, right: number, y: number, placed: readonly Placed[]): boolean {
  return placed.some(
    (entry) =>
      Math.abs(entry.y - y) < ROW_HEIGHT_PX && left < entry.right && entry.left < right,
  )
}

/**
 * Labels go to the right of their point, or to the left when that would run off
 * the plot. A label that would still collide is nudged vertically.
 */
export function placeLabels(
  anchors: readonly LabelAnchor[],
  plotWidth: number,
): readonly PlacedLabel[] {
  const offset = MARKER_CLEARANCE_PX + GAP_PX
  const placed: Placed[] = []
  const results = new Map<string, PlacedLabel>()

  // Left to right, so the crowded right-hand edge is decided with full knowledge.
  for (const anchor of [...anchors].sort((a, b) => a.x - b.x)) {
    const width = estimatedWidth(anchor.length)
    const side: LabelSide = anchor.x + offset + width <= plotWidth ? 'start' : 'end'
    const [left, right] = span(anchor.x, side, width, offset)

    let dy = BASELINE_NUDGE_PX
    while (collides(left, right, anchor.y + dy, placed)) dy += ROW_HEIGHT_PX

    placed.push({ left, right, y: anchor.y + dy })
    results.set(anchor.id, { id: anchor.id, dx: side === 'start' ? offset : -offset, dy, anchor: side })
  }

  return anchors.map(
    (anchor) =>
      results.get(anchor.id) ?? { id: anchor.id, dx: offset, dy: BASELINE_NUDGE_PX, anchor: 'start' },
  )
}
