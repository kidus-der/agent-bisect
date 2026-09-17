import { describe, expect, test } from 'vitest'

import { COST_UNIT_LABEL, formatCalls, formatUsd } from './cost'

describe('formatCalls', () => {
  test('is the primary cost unit, because the server always measures it', () => {
    expect(formatCalls(780.35)).toBe('780 calls')
    expect(formatCalls(1)).toBe('1 call')
    expect(formatCalls(1540)).toBe('1,540 calls')
  })

  test('says nothing rather than rounding a missing count to zero', () => {
    expect(formatCalls(null)).toBe('—')
  })
})

describe('formatUsd', () => {
  test('prints a price the server actually sent', () => {
    expect(formatUsd(1.5607)).toBe('$1.56')
  })

  test('is null when there is no price list, so no caller can print $0.00', () => {
    // Real mode has no USD price list; deriving one from calls would be
    // inventing a number the run never measured.
    expect(formatUsd(null)).toBeNull()
  })
})

describe('COST_UNIT_LABEL', () => {
  test('names calls, so an axis never claims dollars it does not have', () => {
    expect(COST_UNIT_LABEL).toBe('model calls')
  })
})
