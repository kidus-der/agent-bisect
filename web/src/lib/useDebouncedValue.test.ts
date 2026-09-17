import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { useDebouncedValue } from './useDebouncedValue'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useDebouncedValue', () => {
  test('returns the first value immediately', () => {
    expect(renderHook(() => useDebouncedValue('a', 200)).result.current).toBe('a')
  })

  test('trails a change by the delay', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 200), {
      initialProps: { value: 'a' },
    })
    rerender({ value: 'ab' })
    expect(result.current).toBe('a')
    act(() => void vi.advanceTimersByTime(200))
    expect(result.current).toBe('ab')
  })

  test('collapses a burst of keystrokes into one settled value', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 200), {
      initialProps: { value: '' },
    })
    for (const value of ['r', 're', 'ref', 'refu']) {
      rerender({ value })
      act(() => void vi.advanceTimersByTime(50))
    }
    expect(result.current).toBe('')
    act(() => void vi.advanceTimersByTime(200))
    expect(result.current).toBe('refu')
  })
})
