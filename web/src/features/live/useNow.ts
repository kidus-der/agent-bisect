import { useEffect, useState } from 'react'

/**
 * A clock that ticks on an interval, for rendering ages.
 *
 * Coarse on purpose: a per-second tick re-renders the whole page for a label
 * that reads "12s ago" either way, and the feed only needs to be right to the
 * granularity it prints. Stops when the tab is hidden, like the stream.
 */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'hidden') return
      setNow(Date.now())
    }
    const timer = window.setInterval(tick, intervalMs)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [intervalMs])

  return now
}
