import { describe, expect, test } from 'vitest'

import { fillBinGaps, maxBinCount, totalBinCount } from './costBins'

describe('fillBinGaps', () => {
  test('puts back the bins the API left out, at zero', () => {
    // Arrange — the fixture skips 1600-2000 entirely.
    const bins = [
      { calls_low: 1200, calls_high: 1600, count: 3 },
      { calls_low: 2000, calls_high: 2400, count: 1 },
    ]

    // Act
    const filled = fillBinGaps(bins)

    // Assert
    expect(filled).toEqual([
      { calls_low: 1200, calls_high: 1600, count: 3 },
      { calls_low: 1600, calls_high: 2000, count: 0 },
      { calls_low: 2000, calls_high: 2400, count: 1 },
    ])
  })

  test('sorts bins that arrive out of order', () => {
    // Arrange / Act
    const filled = fillBinGaps([
      { calls_low: 400, calls_high: 800, count: 2 },
      { calls_low: 0, calls_high: 400, count: 5 },
    ])

    // Assert
    expect(filled.map((bin) => bin.calls_low)).toEqual([0, 400])
  })

  test('leaves a contiguous series untouched', () => {
    // Arrange
    const bins = [
      { calls_low: 0, calls_high: 400, count: 13 },
      { calls_low: 400, calls_high: 800, count: 34 },
    ]

    // Assert
    expect(fillBinGaps(bins)).toEqual(bins)
  })

  test('returns nothing for an empty histogram', () => {
    expect(fillBinGaps([])).toEqual([])
  })
})

describe('bin totals', () => {
  const bins = [
    { calls_low: 0, calls_high: 400, count: 13 },
    { calls_low: 400, calls_high: 800, count: 34 },
  ]

  test('reports the tallest bin', () => {
    expect(maxBinCount(bins)).toBe(34)
  })

  test('reports how many diagnoses the histogram covers', () => {
    expect(totalBinCount(bins)).toBe(47)
  })

  test('reports zero for an empty histogram', () => {
    expect(maxBinCount([])).toBe(0)
    expect(totalBinCount([])).toBe(0)
  })
})
