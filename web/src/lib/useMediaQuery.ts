import { useCallback, useSyncExternalStore } from 'react'

/**
 * Subscribes to a media query. `useSyncExternalStore` rather than an effect, so
 * a layout that depends on width is never rendered one frame wrong.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window.matchMedia !== 'function') return () => undefined
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    [query],
  )
  const getSnapshot = useCallback(
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : false),
    [query],
  )
  // No DOM during prerender: assume the narrow layout and let the client correct it.
  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}
