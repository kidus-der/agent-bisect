/**
 * Band geometry shared by the tape, the heat stripe under it and the minimap,
 * so all three stay pixel-aligned at any step count.
 */
import { scaleBand } from '@visx/scale'

/** Below this a cell stops being a readable target, so the tape scrolls instead. */
export const MIN_CELL_WIDTH_PX = 30
/** Above this a cell stops reading as an instrument cell and becomes an empty card. */
export const MAX_CELL_WIDTH_PX = 58
const PADDING_INNER = 0.14

export interface TimelineGeometryInput {
  readonly nSteps: number
  readonly availableWidth: number
  readonly minCellWidth?: number
  readonly maxCellWidth?: number
}

export interface TimelineGeometry {
  readonly nSteps: number
  /** Width of the scrollable content; equals the container when it fits. */
  readonly contentWidth: number
  readonly bandWidth: number
  /** Left edge of a 1-based step's cell. */
  readonly x: (step: number) => number
  readonly center: (step: number) => number
  /** Nearest step to a content-space x, clamped to the tape. */
  readonly stepAt: (x: number) => number
  readonly scrolls: boolean
}

export function timelineGeometry({
  nSteps,
  availableWidth,
  minCellWidth = MIN_CELL_WIDTH_PX,
  maxCellWidth = MAX_CELL_WIDTH_PX,
}: TimelineGeometryInput): TimelineGeometry {
  const steps = Math.max(1, nSteps)
  // d3's band: bandwidth = range * (1 - padding) / (n - padding). Invert it to get
  // the range that puts a cell exactly at a given width.
  const rangeFor = (cellWidth: number): number =>
    (cellWidth * (steps - PADDING_INNER)) / (1 - PADDING_INNER)
  const required = rangeFor(minCellWidth)
  const capped = rangeFor(maxCellWidth)
  const contentWidth = Math.min(Math.max(required, availableWidth), Math.max(required, capped))
  const slot = contentWidth / (steps - PADDING_INNER)
  const scale = scaleBand<number>({
    domain: Array.from({ length: steps }, (_, index) => index + 1),
    range: [0, contentWidth],
    paddingInner: PADDING_INNER,
  })
  const bandWidth = scale.bandwidth()
  const x = (step: number): number => scale(clampStep(step, steps)) ?? 0
  return {
    nSteps: steps,
    contentWidth,
    bandWidth,
    x,
    center: (step) => x(step) + bandWidth / 2,
    stepAt: (value) => clampStep(Math.floor(value / slot) + 1, steps),
    scrolls: required > availableWidth,
  }
}

export function clampStep(step: number, nSteps: number): number {
  if (!Number.isFinite(step)) return 1
  return Math.min(Math.max(Math.round(step), 1), Math.max(1, nSteps))
}
