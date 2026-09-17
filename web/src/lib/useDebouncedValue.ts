import { useEffect, useState } from 'react'

/** Trails `value` by `delayMs`. Used to keep a keystroke from becoming a request. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    if (Object.is(debounced, value)) return undefined
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs, debounced])

  return debounced
}
