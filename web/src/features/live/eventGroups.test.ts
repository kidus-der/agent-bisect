import { describe, expect, test } from 'vitest'

import { formatAge, groupEvents, parseEvent } from './eventGroups'
import type { LiveEvent } from './liveBuffer'

function event(seconds: number, message: string, level: LiveEvent['level'] = 'info'): LiveEvent {
  return { ts: new Date(Date.UTC(2026, 8, 17, 10, 0, seconds)).toISOString(), level, message }
}

describe('parseEvent', () => {
  test('lifts the simulated marker, the phase and the batch out of a tick', () => {
    expect(parseEvent('simulated: blame batch 29827852 progressed')).toEqual({
      simulated: true,
      phase: 'blame',
      batch: '29827852',
      detail: 'progressed',
    })
  })

  test('reads an unsimulated tick the same way', () => {
    expect(parseEvent('eval batch 41 progressed')).toMatchObject({
      simulated: false,
      phase: 'eval',
      batch: '41',
    })
  })

  test('passes through a message it has not seen before, untouched', () => {
    // The unfamiliar message is exactly the one worth reading in full.
    const message = 'rate limiter tripped; backing off for 4s'
    expect(parseEvent(message)).toEqual({
      simulated: false,
      phase: null,
      batch: null,
      detail: message,
    })
  })
})

describe('groupEvents', () => {
  test('collapses consecutive ticks for one batch and counts them', () => {
    // Arrange
    const ticks = [
      event(12, 'simulated: blame batch 42 progressed'),
      event(10, 'simulated: blame batch 42 progressed'),
      event(8, 'simulated: blame batch 42 progressed'),
    ]

    // Act
    const groups = groupEvents(ticks)

    // Assert — one entry, counted, keeping the newest timestamp.
    expect(groups).toHaveLength(1)
    expect(groups[0]?.count).toBe(3)
    expect(groups[0]?.ts).toBe(ticks[0]?.ts)
  })

  test('keeps different batches apart', () => {
    const groups = groupEvents([
      event(12, 'simulated: blame batch 42 progressed'),
      event(10, 'simulated: eval batch 43 progressed'),
      event(8, 'simulated: blame batch 42 progressed'),
    ])
    expect(groups.map((group) => group.batch)).toEqual(['42', '43', '42'])
  })

  test('never merges across levels, so a warning is not hidden inside a run of info', () => {
    const groups = groupEvents([
      event(12, 'simulated: blame batch 42 progressed'),
      event(10, 'simulated: blame batch 42 progressed', 'warn'),
    ])
    expect(groups).toHaveLength(2)
  })

  test('leaves unrecognised messages as their own entries', () => {
    const groups = groupEvents([event(12, 'reconnected'), event(10, 'reconnected')])
    expect(groups).toHaveLength(2)
  })

  test('is empty for an empty feed', () => {
    expect(groupEvents([])).toEqual([])
  })
})

describe('formatAge', () => {
  const now = Date.UTC(2026, 8, 17, 10, 5, 0)

  test('reads seconds, minutes and hours', () => {
    expect(formatAge(new Date(now - 2_000).toISOString(), now)).toBe('now')
    expect(formatAge(new Date(now - 12_000).toISOString(), now)).toBe('12s ago')
    expect(formatAge(new Date(now - 240_000).toISOString(), now)).toBe('4m ago')
    expect(formatAge(new Date(now - 7_200_000).toISOString(), now)).toBe('2h ago')
  })

  test('never reports a negative age from a clock that runs ahead', () => {
    expect(formatAge(new Date(now + 5_000).toISOString(), now)).toBe('now')
  })

  test('reports an unparseable timestamp as unknown', () => {
    expect(formatAge('not a date', now)).toBe('—')
  })
})
