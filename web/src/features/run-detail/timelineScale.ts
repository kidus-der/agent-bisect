/**
 * Band geometry shared by the tape, the heat stripe under it and the minimap,
 * so all three stay pixel-aligned at any step count.
 */
import { scaleBand } from '@visx/scale'

/** Below this a cell stops being a readable target, so the tape scrolls instead. */
export const MIN_CELL_WIDTH_PX = 30
const PADDING_INNER = 0.14

export interface TimelineGeometryInput {
  readonly nSteps: number
  readonly availableWidth: number
  readonly minCellWidth?: number
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
}: TimelineGeometryInput): TimelineGeometry {
  const steps = Math.max(1, nSteps)
  // The gap is part of the slot, so the slot has to be wider than the cell itself.
  const required = (steps * minCellWidth) / (1 - PADDING_INNER)
  const contentWidth = Math.max(required, availableWidth)
  const slot = contentWidth / steps
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
