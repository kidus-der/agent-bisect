/**
 * Bounded state for a stream that never ends.
 *
 * The server re-sends a whole snapshot every couple of seconds, so the series,
 * budget, rate limit and jobs are replaced wholesale and cannot grow. The event
 * feed is the one part that accumulates, so it is a ring: newest first, capped,
 * de-duplicated, and the oldest entries are dropped rather than kept forever.
 */
import type { Schemas } from '@/api/client'

export type LiveEvent = Readonly<Schemas['LiveEvent']>

/** Roughly a minute of events at the server's ~2s cadence, with room to spare. */
export const EVENT_BUFFER_LIMIT = 60

function eventKey(event: LiveEvent): string {
  return `${event.ts}|${event.level}|${event.message}`
}

/**
 * Merges a snapshot's events into the ring. Snapshots overlap heavily, so
 * anything already held is dropped rather than repeated, and the result is
 * newest first and never longer than `limit`.
 */
export function mergeEvents(
  existing: readonly LiveEvent[],
  incoming: readonly LiveEvent[],
  limit: number = EVENT_BUFFER_LIMIT,
): readonly LiveEvent[] {
  if (incoming.length === 0) return existing
  const seen = new Set(existing.map(eventKey))
  const fresh = incoming.filter((event) => !seen.has(eventKey(event)))
  if (fresh.length === 0) return existing
  const merged = [...fresh, ...existing].sort(
    (a, b) => Date.parse(b.ts) - Date.parse(a.ts) || eventKey(a).localeCompare(eventKey(b)),
  )
  return merged.slice(0, limit)
}

/** Exponential backoff, capped. Deterministic: a flapping server must not surprise us. */
export const FIRST_RETRY_MS = 1000
export const MAX_RETRY_MS = 15_000

export function backoffDelay(attempt: number): number {
  if (attempt <= 0) return FIRST_RETRY_MS
  return Math.min(MAX_RETRY_MS, FIRST_RETRY_MS * 2 ** attempt)
}
