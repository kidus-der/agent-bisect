import { describe, expect, test } from 'vitest'

import { contrastRatio, mixHex, parseHex, toHex, withAlpha } from './color'

describe('color', () => {
  test('black on white is the maximum contrast, 21:1', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
  })

  test('contrast is symmetric and 1:1 for identical colours', () => {
    expect(contrastRatio('#4CC9F0', '#0B0D12')).toBeCloseTo(contrastRatio('#0B0D12', '#4CC9F0'), 10)
    expect(contrastRatio('#123456', '#123456')).toBe(1)
  })

  test('matches the ratios published in direction.md', () => {
    expect(contrastRatio('#E8EBF2', '#0B0D12')).toBeCloseTo(16.3, 1)
    expect(contrastRatio('#5B6478', '#12151C')).toBeCloseTo(3.08, 2)
  })

  test('mixHex composites a foreground over an opaque background', () => {
    expect(mixHex('#FFFFFF', '#000000', 0.5)).toBe('#808080')
    expect(mixHex('#FF0000', '#0000FF', 0)).toBe('#0000FF')
    expect(mixHex('#FF0000', '#0000FF', 1)).toBe('#FF0000')
  })

  test('parseHex rejects anything that is not a 6-digit hex', () => {
    expect(() => parseHex('#FFF')).toThrow(/6-digit hex/)
    expect(() => parseHex('rgb(0,0,0)')).toThrow(/6-digit hex/)
  })

  test('toHex clamps channels and withAlpha emits modern rgb()', () => {
    expect(toHex({ r: 300, g: -4, b: 127.6 })).toBe('#FF0080')
    expect(withAlpha('#4CC9F0', 0.35)).toBe('rgb(76 201 240 / 0.35)')
  })
})
