import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { EVENT_BUFFER_LIMIT, FIRST_RETRY_MS, MAX_RETRY_MS } from './liveBuffer'
import {
  type EventSourceLike,
  OFFLINE_AFTER_ATTEMPTS,
  SNAPSHOT_EVENT,
  useLiveStream,
} from './useLiveStream'

type Listener = (event: MessageEvent<string>) => void

/** A fake EventSource that never touches the network and records its own lifecycle. */
class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = []
  readonly url: string
  closed = false
  private readonly listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close(): void {
    this.closed = true
  }

  emit(type: string, data: string): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data } as MessageEvent<string>)
    }
  }

  static get live(): FakeEventSource[] {
    return FakeEventSource.instances.filter((instance) => !instance.closed)
  }

  static reset(): void {
    FakeEventSource.instances = []
  }
}

const META = {
  simulated: true,
  data_source: 'fixture',
  total: null,
  page: null,
  limit: null,
  next_cursor: null,
}

function snapshotFrame(seconds: number, eventCount = 1): string {
  const events = Array.from({ length: eventCount }, (_, index) => ({
    ts: new Date(Date.UTC(2026, 8, 17, 10, 0, seconds - index)).toISOString(),
    level: 'info',
    message: `tick ${seconds - index}`,
  }))
  return JSON.stringify({
    success: true,
    error: null,
    meta: META,
    data: {
      calls_series: [{ ts: '2026-09-17T10:00:00+00:00', model: 'm', calls_per_minute: 12 }],
      budget: { used: 10, cap: 100 },
      rate_limit: { limiter_rpm: 40, current_rpm: 12, headroom_rpm: 28 },
      jobs: [],
      events,
    },
  })
}

function setup(hidden = false) {
  return renderHook(() =>
    useLiveStream({
      path: '/api/live/stream',
      createEventSource: (url) => new FakeEventSource(url),
      isHidden: () => hidden,
    }),
  )
}

beforeEach(() => {
  FakeEventSource.reset()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useLiveStream connection', () => {
  test('opens one connection and reports it live once a snapshot arrives', () => {
    // Arrange
    const { result } = setup()
    expect(result.current.connection).toBe('connecting')

    // Act
    act(() => {
      FakeEventSource.instances[0]?.emit(SNAPSHOT_EVENT, snapshotFrame(10))
    })

    // Assert
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(result.current.connection).toBe('live')
    expect(result.current.snapshot?.budget.used).toBe(10)
    expect(result.current.updates).toBe(1)
  })

  test('counts every snapshot it receives', () => {
    // Arrange
    const { result } = setup()

    // Act
    act(() => {
      FakeEventSource.instances[0]?.emit(SNAPSHOT_EVENT, snapshotFrame(10))
    })
    act(() => {
      FakeEventSource.instances[0]?.emit(SNAPSHOT_EVENT, snapshotFrame(12))
    })

    // Assert
    expect(result.current.updates).toBe(2)
  })

  test('ignores a malformed frame instead of tearing down the connection', () => {
    // Arrange
    const { result } = setup()
    act(() => {
      FakeEventSource.instances[0]?.emit(SNAPSHOT_EVENT, snapshotFrame(10))
    })

    // Act
    act(() => {
      FakeEventSource.instances[0]?.emit(SNAPSHOT_EVENT, 'not json at all')
    })

    // Assert
    expect(result.current.connection).toBe('live')
    expect(result.current.updates).toBe(1)
  })

  test('surfaces a not_available payload without inventing a snapshot', () => {
    // Arrange
    const { result } = setup()

    // Act
    act(() => {
      FakeEventSource.instances[0]?.emit(
        SNAPSHOT_EVENT,
        JSON.stringify({
          success: true,
          error: null,
          meta: META,
          data: { status: 'not_available', reason: 'no ledger yet' },
        }),
      )
    })

    // Assert
    expect(result.current.snapshot).toBeNull()
    expect(result.current.notAvailableReason).toBe('no ledger yet')
  })
})

describe('useLiveStream reconnection', () => {
  test('closes the socket on error rather than letting it hammer the server', () => {
    // Arrange
    const { result } = setup()

    // Act
    act(() => {
      FakeEventSource.instances[0]?.emit('error', '')
    })

    // Assert
    expect(FakeEventSource.instances[0]?.closed).toBe(true)
    expect(result.current.connection).toBe('reconnecting')
  })

  test('waits the first backoff before reopening', () => {
    // Arrange
    setup()
    act(() => {
      FakeEventSource.instances[0]?.emit('error', '')
    })

    // Act — nothing yet just short of the delay.
    act(() => {
      vi.advanceTimersByTime(FIRST_RETRY_MS - 1)
    })
    expect(FakeEventSource.instances).toHaveLength(1)
    act(() => {
      vi.advanceTimersByTime(1)
    })

    // Assert
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  test('backs off further with each consecutive failure', () => {
    // Arrange
    setup()

    // Act — fail, wait 1s, fail again; the second wait must be 2s.
    act(() => {
      FakeEventSource.instances[0]?.emit('error', '')
      vi.advanceTimersByTime(FIRST_RETRY_MS)
    })
    act(() => {
      FakeEventSource.instances[1]?.emit('error', '')
      vi.advanceTimersByTime(FIRST_RETRY_MS)
    })
    expect(FakeEventSource.instances).toHaveLength(2)

    act(() => {
      vi.advanceTimersByTime(FIRST_RETRY_MS)
    })

    // Assert
    expect(FakeEventSource.instances).toHaveLength(3)
  })

  test('reports offline after repeated failures but keeps retrying', () => {
    // Arrange
    const { result } = setup()

    // Act
    for (let attempt = 0; attempt < OFFLINE_AFTER_ATTEMPTS; attempt += 1) {
      act(() => {
        FakeEventSource.instances.at(-1)?.emit('error', '')
        vi.advanceTimersByTime(MAX_RETRY_MS)
      })
    }

    // Assert
    expect(result.current.connection).toBe('offline')
    expect(FakeEventSource.instances.length).toBeGreaterThan(OFFLINE_AFTER_ATTEMPTS)
  })

  test('resets the backoff once a snapshot arrives again', () => {
    // Arrange
    const { result } = setup()
    act(() => {
      FakeEventSource.instances[0]?.emit('error', '')
      vi.advanceTimersByTime(FIRST_RETRY_MS)
    })

    // Act
    act(() => {
      FakeEventSource.instances[1]?.emit(SNAPSHOT_EVENT, snapshotFrame(20))
    })
    act(() => {
      FakeEventSource.instances[1]?.emit('error', '')
    })
    act(() => {
      vi.advanceTimersByTime(FIRST_RETRY_MS)
    })

    // Assert — back to the first, shortest delay.
    expect(result.current.connection).toBe('reconnecting')
    expect(FakeEventSource.instances).toHaveLength(3)
  })

  test('retryNow reopens immediately without waiting out the backoff', () => {
    // Arrange
    const { result } = setup()
    act(() => {
      FakeEventSource.instances[0]?.emit('error', '')
    })

    // Act
    act(() => {
      result.current.retryNow()
    })

    // Assert
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(result.current.connection).toBe('connecting')
  })
})

describe('useLiveStream lifecycle', () => {
  test('opens nothing at all while the tab is hidden', () => {
    // Arrange / Act
    const { result } = setup(true)

    // Assert
    expect(FakeEventSource.instances).toHaveLength(0)
    expect(result.current.connection).toBe('paused')
  })

  test('closes the socket on unmount, so nothing is left streaming', () => {
    // Arrange
    const { unmount } = setup()

    // Act
    unmount()

    // Assert
    expect(FakeEventSource.live).toHaveLength(0)
  })

  test('keeps the event feed bounded however many snapshots arrive', () => {
    // Arrange
    const { result } = setup()

    // Act — far more distinct events than the ring holds.
    for (let tick = 0; tick < EVENT_BUFFER_LIMIT * 3; tick += 1) {
      act(() => {
        FakeEventSource.instances[0]?.emit(SNAPSHOT_EVENT, snapshotFrame(tick))
      })
    }

    // Assert
    expect(result.current.events.length).toBeLessThanOrEqual(EVENT_BUFFER_LIMIT)
    expect(result.current.updates).toBe(EVENT_BUFFER_LIMIT * 3)
  })
})
