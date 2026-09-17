import { describe, expect, test } from 'vitest'

import { formatEffect, formatInterval, formatNumber } from './format'

describe('format', () => {
  test('effects are signed with a real minus sign', () => {
    expect(formatEffect(0.75)).toBe('+0.75')
    expect(formatEffect(-0.125)).toBe('−0.13')
  })

  test('zero carries no sign, even negative zero after rounding', () => {
    expect(formatEffect(0)).toBe('0.00')
    expect(formatEffect(-0.001)).toBe('0.00')
  })

  test('non-finite values are never printed as numbers', () => {
    expect(formatEffect(Number.NaN)).toBe('n/a')
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe('n/a')
  })

  test('intervals are bracketed and signed', () => {
    expect(formatInterval(-0.18, 0.26)).toBe('[−0.18, +0.26]')
  })

  test('formatNumber applies grouping, decimals, prefix and suffix', () => {
    expect(formatNumber(1240)).toBe('1,240')
    expect(formatNumber(3.361, { decimals: 2, prefix: '$' })).toBe('$3.36')
    expect(formatNumber(58, { suffix: '%' })).toBe('58%')
    expect(formatNumber(0.5, { decimals: 2, signed: true })).toBe('+0.50')
  })
})
