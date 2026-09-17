/** Inner width of the palette's detail pane; the stripe is sized to fill it at any step count. */
const STRIPE_WIDTH_PX = 256
const CELL_GAP_PX = 2
const MAX_CELL_PX = 14
const MIN_CELL_PX = 2

export function stripeCellWidth(stepCount: number): number {
  if (stepCount <= 0) return MAX_CELL_PX
  const fitted = Math.floor((STRIPE_WIDTH_PX + CELL_GAP_PX) / stepCount) - CELL_GAP_PX
  return Math.min(MAX_CELL_PX, Math.max(MIN_CELL_PX, fitted))
}
