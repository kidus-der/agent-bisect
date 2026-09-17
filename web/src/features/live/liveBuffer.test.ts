import { describe, expect, test } from 'vitest'

import {
  EVENT_BUFFER_LIMIT,
  FIRST_RETRY_MS,
  MAX_RETRY_MS,
  type LiveEvent,
  backoffDelay,
  mergeEvents,
} from './liveBuffer'

function event(seconds: number, message = 'tick'): LiveEvent {
  const ts = new Date(Date.UTC(2026, 8, 17, 10, 0, seconds)).toISOString()
  return { ts, level: 'info', message }
}

describe('mergeEvents', () => {
  test('puts the newest event first', () => {
    // Arrange / Act
    const merged = mergeEvents([event(1)], [event(5)])

    // Assert
    expect(merged.map((entry) => entry.message)).toHaveLength(2)
    expect(Date.parse(merged[0]?.ts ?? '')).toBeGreaterThan(Date.parse(merged[1]?.ts ?? ''))
  })

  test('drops events already held, because snapshots overlap', () => {
    // Arrange
    const existing = [event(3), event(2), event(1)]

    // Act — the next snapshot repeats two of them and adds one.
    const merged = mergeEvents(existing, [event(4), event(3), event(2)])

    // Assert
    expect(merged).toHaveLength(4)
  })

  test('returns the same array when nothing is new, so nothing re-renders', () => {
    // Arrange
    const existing = [event(2), event(1)]

    // Act / Assert
    expect(mergeEvents(existing, [event(2)])).toBe(existing)
    expect(mergeEvents(existing, [])).toBe(existing)
  })

  test('never grows past the limit, however long the stream runs', () => {
    // Arrange — far more events than the buffer holds.
    const flood = Array.from({ length: EVENT_BUFFER_LIMIT * 4 }, (_, index) =>
      event(index, `event-${index}`),
    )

    // Act
    const merged = flood.reduce<readonly LiveEvent[]>(
      (buffer, entry) => mergeEvents(buffer, [entry]),
      [],
    )

    // Assert
    expect(merged).toHaveLength(EVENT_BUFFER_LIMIT)
  })

  test('keeps the newest events when it overflows, not the oldest', () => {
    // Arrange
    const flood = Array.from({ length: EVENT_BUFFER_LIMIT + 5 }, (_, index) =>
      event(index, `event-${index}`),
    )

    // Act
    const merged = mergeEvents([], flood)

    // Assert
    expect(merged[0]?.message).toBe(`event-${EVENT_BUFFER_LIMIT + 4}`)
    expect(merged.at(-1)?.message).toBe(`event-5`)
  })

  test('does not mutate the buffer it was given', () => {
    // Arrange
    const existing = [event(1)]

    // Act
    mergeEvents(existing, [event(2)])

    // Assert
    expect(existing).toHaveLength(1)
  })
})

describe('backoffDelay', () => {
  test('waits one second before the first retry', () => {
    expect(backoffDelay(0)).toBe(FIRST_RETRY_MS)
  })

  test('doubles with each consecutive failure', () => {
    expect(backoffDelay(1)).toBe(2000)
    expect(backoffDelay(2)).toBe(4000)
    expect(backoffDelay(3)).toBe(8000)
  })

  test('stops doubling at the cap, so a dead server is retried forever but gently', () => {
    expect(backoffDelay(10)).toBe(MAX_RETRY_MS)
    expect(backoffDelay(100)).toBe(MAX_RETRY_MS)
  })
})
