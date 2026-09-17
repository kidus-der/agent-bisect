import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'

import { stubMatchMedia } from '@/test/setup'

import { useMediaQuery } from './useMediaQuery'

afterEach(() => stubMatchMedia(() => false))

describe('useMediaQuery', () => {
  test('reports a matching query', () => {
    stubMatchMedia((query) => query === '(min-width: 768px)')
    expect(renderHook(() => useMediaQuery('(min-width: 768px)')).result.current).toBe(true)
  })

  test('reports a query that does not match', () => {
    stubMatchMedia(() => false)
    expect(renderHook(() => useMediaQuery('(min-width: 768px)')).result.current).toBe(false)
  })

  test('falls back to false where matchMedia is unavailable', () => {
    Reflect.deleteProperty(window, 'matchMedia')
    expect(renderHook(() => useMediaQuery('(min-width: 768px)')).result.current).toBe(false)
  })
})
