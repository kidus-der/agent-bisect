import { describe, expect, test } from 'vitest'

import { formatPValue, formatPercent, newcombeInterval, wilsonInterval } from './stats'

describe('wilsonInterval', () => {
  test('brackets the observed rate', () => {
    // Arrange
    const rate = 0.9651
    const n = 86

    // Act
    const interval = wilsonInterval(rate, n)

    // Assert
    expect(interval).not.toBeNull()
    expect(interval?.low).toBeLessThan(rate)
    expect(interval?.high).toBeGreaterThan(rate)
  })

  test('matches the published bound for 81 of 100 successes', () => {
    // Arrange / Act
    const interval = wilsonInterval(0.81, 100)

    // Assert — Wilson 95% for 81/100 is [0.7215, 0.8745].
    expect(interval?.low).toBeCloseTo(0.7215, 3)
    expect(interval?.high).toBeCloseTo(0.8745, 3)
  })

  test('stays inside zero and one at the extremes', () => {
    // Arrange / Act
    const interval = wilsonInterval(1, 10)

    // Assert
    expect(interval?.low).toBeGreaterThan(0)
    expect(interval?.high).toBeLessThanOrEqual(1)
  })

  test('returns null when n is not a usable sample size', () => {
    expect(wilsonInterval(0.5, 0)).toBeNull()
    expect(wilsonInterval(0.5, Number.NaN)).toBeNull()
    expect(wilsonInterval(Number.NaN, 20)).toBeNull()
  })

  test('narrows as n grows', () => {
    // Arrange / Act
    const small = wilsonInterval(0.8, 20)
    const large = wilsonInterval(0.8, 2000)

    // Assert
    const smallWidth = (small?.high ?? 0) - (small?.low ?? 0)
    const largeWidth = (large?.high ?? 0) - (large?.low ?? 0)
    expect(largeWidth).toBeLessThan(smallWidth)
  })
})

describe('newcombeInterval', () => {
  test('brackets the difference of the two rates', () => {
    // Arrange
    const base = { rate: 0.875, n: 96 }
    const head = { rate: 0.5833, n: 96 }

    // Act
    const interval = newcombeInterval(head.rate, head.n, base.rate, base.n)

    // Assert
    expect(interval?.value).toBeCloseTo(head.rate - base.rate, 6)
    expect(interval?.low).toBeLessThan(interval?.value ?? 0)
    expect(interval?.high).toBeGreaterThan(interval?.value ?? 0)
  })

  test('excludes zero when the two rates are far apart', () => {
    // Arrange / Act
    const interval = newcombeInterval(0.2, 96, 0.9, 96)

    // Assert
    expect(interval?.high).toBeLessThan(0)
  })

  test('includes zero when the two rates are close', () => {
    // Arrange / Act
    const interval = newcombeInterval(0.79, 40, 0.83, 40)

    // Assert
    expect(interval?.low).toBeLessThan(0)
    expect(interval?.high).toBeGreaterThan(0)
  })

  test('returns null when either arm has no sample', () => {
    expect(newcombeInterval(0.5, 0, 0.5, 20)).toBeNull()
    expect(newcombeInterval(0.5, 20, 0.5, 0)).toBeNull()
  })
})

describe('formatPercent', () => {
  test('renders a rate as a percentage with one decimal by default', () => {
    expect(formatPercent(0.9651)).toBe('96.5%')
  })

  test('honours the requested precision', () => {
    expect(formatPercent(0.9651, 0)).toBe('97%')
  })

  test('reports a non-finite rate as not available', () => {
    expect(formatPercent(Number.NaN)).toBe('n/a')
  })
})

describe('formatPValue', () => {
  test('renders an ordinary p value at three decimals', () => {
    expect(formatPValue(0.023)).toBe('0.023')
  })

  test('renders a very small p value as a bound', () => {
    expect(formatPValue(0.0001)).toBe('< 0.001')
  })

  test('reports a non-finite p value as not available', () => {
    expect(formatPValue(Number.NaN)).toBe('n/a')
  })
})
