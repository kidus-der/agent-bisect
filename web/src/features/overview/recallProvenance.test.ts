import { describe, expect, test } from 'vitest'

import type { RecallPoint } from './api'
import { splitRecall } from './recallProvenance'

const POINTS: readonly RecallPoint[] = [
  { m: 1, recall: 0.42 },
  { m: 2, recall: 0.61 },
  { m: 3, recall: 0.74 },
  { m: 5, recall: 0.88 },
  { m: 10, recall: 0.96 },
]

describe('splitRecall', () => {
  test('separates the replayed shortlist from the judge ranking beyond it', () => {
    // Act
    const { measured, ranked } = splitRecall(POINTS, 3)

    // Assert
    expect(measured.map((point) => point.m)).toEqual([1, 2, 3])
    expect(ranked.map((point) => point.m)).toEqual([3, 5, 10])
  })

  test('repeats the boundary point so the two segments meet', () => {
    // Otherwise the curve has a visible gap at exactly the m the reader cares
    // most about — where the evidence changes kind.
    const { measured, ranked } = splitRecall(POINTS, 3)
    expect(measured.at(-1)).toEqual(ranked[0])
  })

  test('claims nothing beyond the measurement when everything was replayed', () => {
    const { measured, ranked } = splitRecall(POINTS, 10)
    expect(measured).toHaveLength(POINTS.length)
    expect(ranked).toHaveLength(1)
  })

  test('treats every point as judge ranking when nothing was replayed', () => {
    const { measured, ranked } = splitRecall(POINTS, 0)
    expect(measured).toHaveLength(0)
    expect(ranked).toHaveLength(POINTS.length)
  })
})
