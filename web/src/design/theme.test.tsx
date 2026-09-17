import { act, renderHook } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { stubMatchMedia } from '@/test/setup'

import {
  ensureTheme,
  getTheme,
  resolveInitialTheme,
  setTheme,
  toggleTheme,
  useTheme,
} from './theme'
import { THEME_STORAGE_KEY } from './tokens'

describe('theme', () => {
  test('defaults to dark when nothing is stored and the OS has no light preference', () => {
    stubMatchMedia(() => false)
    expect(resolveInitialTheme()).toBe('dark')
  })

  test('follows prefers-color-scheme: light when nothing is stored', () => {
    stubMatchMedia((query) => query.includes('light'))
    expect(resolveInitialTheme()).toBe('light')
    stubMatchMedia(() => false)
  })

  test('a stored choice wins over the OS preference', () => {
    stubMatchMedia((query) => query.includes('light'))
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    expect(resolveInitialTheme()).toBe('dark')
    stubMatchMedia(() => false)
  })

  test('ignores a corrupt stored value', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia')
    expect(resolveInitialTheme()).toBe('dark')
  })

  test('setTheme writes data-theme on <html> and persists it', () => {
    setTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })

  test('toggleTheme flips and returns the new theme', () => {
    setTheme('dark')
    expect(toggleTheme()).toBe('light')
    expect(toggleTheme()).toBe('dark')
    expect(getTheme()).toBe('dark')
  })

  test('ensureTheme fills in the attribute when the inline script did not run', () => {
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
    ensureTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  test('useTheme re-renders when the attribute changes', async () => {
    setTheme('dark')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
    await act(async () => {
      result.current.toggle()
      await Promise.resolve()
    })
    expect(result.current.theme).toBe('light')
  })
})
