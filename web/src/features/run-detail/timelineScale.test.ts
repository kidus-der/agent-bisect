import { describe, expect, it } from 'vitest'

import { MAX_CELL_WIDTH_PX, MIN_CELL_WIDTH_PX, timelineGeometry } from './timelineScale'

describe('timelineGeometry', () => {
  it('spreads a short run across the available width', () => {
    // Arrange / Act
    const geometry = timelineGeometry({ nSteps: 20, availableWidth: 900 })

    // Assert
    expect(geometry.contentWidth).toBe(900)
    expect(geometry.scrolls).toBe(false)
    expect(geometry.bandWidth).toBeGreaterThan(MIN_CELL_WIDTH_PX)
  })

  it('stops a very short run from becoming a row of empty cards', () => {
    // Arrange / Act: 6 cells over 1400px would be 230px each.
    const geometry = timelineGeometry({ nSteps: 6, availableWidth: 1400 })

    // Assert
    expect(geometry.bandWidth).toBeLessThanOrEqual(MAX_CELL_WIDTH_PX)
    expect(geometry.contentWidth).toBeLessThan(1400)
    expect(geometry.scrolls).toBe(false)
  })

  it('lets a 12-step tape use a wide panel instead of floating in the middle', () => {
    // Arrange / Act: the run-detail panel width beside the blame rail.
    const geometry = timelineGeometry({ nSteps: 12, availableWidth: 1100 })

    // Assert: cells grow towards the cap rather than stopping at a token size.
    expect(geometry.bandWidth).toBeGreaterThan(60)
    expect(geometry.contentWidth).toBe(1100)
  })

  it('never shrinks a cell below a usable target', () => {
    const geometry = timelineGeometry({ nSteps: 60, availableWidth: 900 })

    expect(geometry.bandWidth).toBeCloseTo(MIN_CELL_WIDTH_PX, 6)
    expect(MIN_CELL_WIDTH_PX).toBeGreaterThanOrEqual(40)
  })

  it('keeps a 60-step run legible by scrolling instead of shrinking the cells', () => {
    const geometry = timelineGeometry({ nSteps: 60, availableWidth: 900 })

    expect(geometry.scrolls).toBe(true)
    expect(geometry.contentWidth).toBeGreaterThan(900)
    expect(geometry.bandWidth).toBeCloseTo(MIN_CELL_WIDTH_PX, 6)
  })

  it('never produces a zero or negative width for a degenerate container', () => {
    const geometry = timelineGeometry({ nSteps: 4, availableWidth: 0 })

    expect(geometry.contentWidth).toBeGreaterThan(0)
    expect(geometry.bandWidth).toBeGreaterThan(0)
  })

  it('maps a step to a band and back from its centre', () => {
    // Arrange
    const geometry = timelineGeometry({ nSteps: 12, availableWidth: 900 })

    // Act / Assert
    for (const step of [1, 5, 12]) {
      expect(geometry.stepAt(geometry.center(step))).toBe(step)
    }
  })

  it('clamps a pointer dragged past either end of the tape', () => {
    const geometry = timelineGeometry({ nSteps: 12, availableWidth: 900 })

    expect(geometry.stepAt(-500)).toBe(1)
    expect(geometry.stepAt(99_999)).toBe(12)
  })

  it('places step 1 at the left edge and the last step at the right', () => {
    const geometry = timelineGeometry({ nSteps: 20, availableWidth: 800 })

    expect(geometry.x(1)).toBeLessThan(geometry.bandWidth)
    expect(geometry.x(20) + geometry.bandWidth).toBeCloseTo(geometry.contentWidth, 0)
  })
})
