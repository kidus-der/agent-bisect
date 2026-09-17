/**
 * Theme state lives on <html data-theme>. index.html sets it before first paint;
 * this module reads, toggles and persists it. Keep the storage key and fallback
 * order in sync with the inline script in index.html.
 */
import { useCallback, useSyncExternalStore } from 'react'

import { THEME_NAMES, THEME_STORAGE_KEY, type ThemeName } from './tokens'

const THEME_ATTRIBUTE = 'data-theme'
const DEFAULT_THEME: ThemeName = 'dark'

function isThemeName(value: unknown): value is ThemeName {
  return typeof value === 'string' && (THEME_NAMES as readonly string[]).includes(value)
}

export function readStoredTheme(): ThemeName | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isThemeName(stored) ? stored : null
  } catch {
    // Storage can be blocked (private mode); the theme still works for the session.
    return null
  }
}

export function resolveInitialTheme(): ThemeName {
  const stored = readStoredTheme()
  if (stored) return stored
  const prefersLight =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: light)').matches
  return prefersLight ? 'light' : DEFAULT_THEME
}

export function getTheme(): ThemeName {
  const current = document.documentElement.getAttribute(THEME_ATTRIBUTE)
  return isThemeName(current) ? current : DEFAULT_THEME
}

export function setTheme(theme: ThemeName): void {
  document.documentElement.setAttribute(THEME_ATTRIBUTE, theme)
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Not persisted; the attribute change above still applies for this session.
  }
}

export function toggleTheme(): ThemeName {
  const next: ThemeName = getTheme() === 'dark' ? 'light' : 'dark'
  setTheme(next)
  return next
}

/** Ensures the attribute exists even if the inline script was stripped (tests, CSP). */
export function ensureTheme(): void {
  if (!isThemeName(document.documentElement.getAttribute(THEME_ATTRIBUTE))) {
    document.documentElement.setAttribute(THEME_ATTRIBUTE, resolveInitialTheme())
  }
}

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: [THEME_ATTRIBUTE],
  })
  return () => observer.disconnect()
}

export interface UseThemeResult {
  readonly theme: ThemeName
  readonly toggle: () => void
}

export function useTheme(): UseThemeResult {
  const theme = useSyncExternalStore(subscribe, getTheme, () => DEFAULT_THEME)
  const toggle = useCallback(() => {
    toggleTheme()
  }, [])
  return { theme, toggle }
}
