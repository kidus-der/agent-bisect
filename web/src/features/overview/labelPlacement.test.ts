import { describe, expect, test } from 'vitest'

import { type LabelAnchor, placeLabels } from './labelPlacement'

const PLOT_WIDTH = 600

function anchor(id: string, x: number, y: number, length = 8): LabelAnchor {
  return { id, x, y, length }
}

describe('placeLabels', () => {
  test('labels a point on its right when there is room', () => {
    const [placed] = placeLabels([anchor('a', 100, 50)], PLOT_WIDTH)
    expect(placed).toMatchObject({ anchor: 'start' })
    expect(placed?.dx).toBeGreaterThan(0)
  })

  test('flips to the left when the label would run off the plot', () => {
    const [placed] = placeLabels([anchor('a', 580, 50, 20)], PLOT_WIDTH)
    expect(placed).toMatchObject({ anchor: 'end' })
    expect(placed?.dx).toBeLessThan(0)
  })

  test('two points at the same cost keep separate labels', () => {
    // The real collision this exists for: Bisect and no-control cost the same.
    const placed = placeLabels(
      [anchor('bisect', 400, 20), anchor('no_control', 402, 120)],
      PLOT_WIDTH,
    )
    expect(placed.every((entry) => entry.anchor === 'start')).toBe(true)
    expect(placed.map((entry) => entry.dy)).toEqual([4, 4])
  })

  test('nudges a label down when two points sit on top of each other', () => {
    const placed = placeLabels([anchor('a', 400, 100), anchor('b', 404, 103)], PLOT_WIDTH)
    const [first, second] = placed
    expect(Math.abs((first?.dy ?? 0) - (second?.dy ?? 0))).toBeGreaterThanOrEqual(12)
  })

  test('separates a right-anchored label that reaches back over a left-anchored one', () => {
    // The real case: Bisect labels rightwards, Re-run live has to label leftwards
    // across it, at almost the same accuracy.
    const anchors = [anchor('bisect', 470, 30, 6), anchor('rerun_live', 535, 44, 11)]
    const placed = placeLabels(anchors, PLOT_WIDTH)
    const rows = placed.map((entry, index) => (anchors[index]?.y ?? 0) + entry.dy)
    expect(placed.map((entry) => entry.anchor)).toEqual(['start', 'end'])
    expect(Math.abs((rows[0] ?? 0) - (rows[1] ?? 0))).toBeGreaterThanOrEqual(18)
  })

  test('returns results in the order it was given, not sorted by x', () => {
    const placed = placeLabels([anchor('right', 400, 10), anchor('left', 10, 10)], PLOT_WIDTH)
    expect(placed.map((entry) => entry.id)).toEqual(['right', 'left'])
  })

  test('a long label near the middle still fits to the right', () => {
    const [placed] = placeLabels([anchor('a', 200, 50, 20)], PLOT_WIDTH)
    expect(placed?.anchor).toBe('start')
  })
})
