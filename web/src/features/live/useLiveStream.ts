/**
 * The SSE connection behind the Live page.
 *
 * Three things a naive `new EventSource(...)` gets wrong here:
 * 1. It reconnects immediately and forever, hammering a server that is down.
 *    This closes the socket on error and reopens on a capped exponential
 *    backoff instead, so a dead server is retried gently.
 * 2. It keeps streaming into a tab nobody is looking at. This closes on
 *    `visibilitychange` and reopens when the tab comes back.
 * 3. Its payloads accumulate. Everything but the event feed is replaced
 *    wholesale; the feed is a bounded ring (`mergeEvents`).
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import type { ResponseMeta, Schemas } from '@/api/client'
import { type NotAvailable, isNotAvailable } from '@/api/payload'

import { type LiveEvent, backoffDelay, mergeEvents } from './liveBuffer'

export type LiveSnapshot = Readonly<Schemas['LiveSnapshot']>

type SocketState = 'connecting' | 'live' | 'reconnecting' | 'offline'

export type LiveConnectionState = SocketState | 'paused'

/** The slice of `EventSource` this hook uses, so a test can hand it a fake. */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void
  close(): void
}

export const SNAPSHOT_EVENT = 'snapshot'
export const DEFAULT_STREAM_PATH = '/api/live/stream'
/** Consecutive failures after which the indicator says "offline" rather than "reconnecting". */
export const OFFLINE_AFTER_ATTEMPTS = 3

export interface UseLiveStreamOptions {
  readonly path?: string
  readonly createEventSource?: (url: string) => EventSourceLike
  /** Injected so a test can drive the pause path without touching `document`. */
  readonly isHidden?: () => boolean
}

export interface LiveStream {
  readonly snapshot: LiveSnapshot | null
  readonly meta: ResponseMeta | null
  readonly events: readonly LiveEvent[]
  readonly connection: LiveConnectionState
  /** How many snapshots have arrived on this page. */
  readonly updates: number
  /** When the newest frame arrived, so a stalled stream is visible. */
  readonly lastFrameAt: number | null
  /** Set when the server answered `not_available`; the page must not draw numbers then. */
  readonly notAvailableReason: string | null
  readonly retryNow: () => void
}

interface ParsedSnapshot {
  readonly snapshot: LiveSnapshot | null
  readonly meta: ResponseMeta | null
  readonly reason: string | null
}

function defaultCreateEventSource(url: string): EventSourceLike {
  return new EventSource(url)
}

function defaultIsHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

/** Parses one `event: snapshot` frame. Returns null for anything malformed. */
export function parseSnapshotFrame(raw: string): ParsedSnapshot | null {
  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof body !== 'object' || body === null) return null
  const envelope = body as { data?: unknown; meta?: unknown; success?: unknown }
  if (envelope.success !== true) return null
  const meta = (envelope.meta ?? null) as ResponseMeta | null
  const data = envelope.data as LiveSnapshot | NotAvailable | null
  if (data === null) return null
  if (isNotAvailable(data)) return { snapshot: null, meta, reason: data.reason }
  return { snapshot: data, meta, reason: null }
}

export function useLiveStream(options: UseLiveStreamOptions = {}): LiveStream {
  const path = options.path ?? DEFAULT_STREAM_PATH
  const createEventSource = options.createEventSource ?? defaultCreateEventSource
  const isHidden = options.isHidden ?? defaultIsHidden

  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null)
  const [meta, setMeta] = useState<ResponseMeta | null>(null)
  const [events, setEvents] = useState<readonly LiveEvent[]>([])
  const [updates, setUpdates] = useState(0)
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null)
  const [notAvailableReason, setNotAvailableReason] = useState<string | null>(null)
  const [socketState, setSocketState] = useState<SocketState>('connecting')
  const [generation, setGeneration] = useState(0)
  // Read at mount, not defaulted to false: a page that mounts in a background
  // tab must not open a socket and close it again on the next commit.
  const [hidden, setHidden] = useState(() => isHidden())

  // Held in refs so changing them never tears down a healthy connection.
  const factoryRef = useRef(createEventSource)
  const isHiddenRef = useRef(isHidden)
  useEffect(() => {
    factoryRef.current = createEventSource
    isHiddenRef.current = isHidden
  })

  const attemptRef = useRef(0)
  const timerRef = useRef<number | null>(null)

  const clearRetry = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const retryNow = useCallback(() => {
    clearRetry()
    attemptRef.current = 0
    setSocketState('connecting')
    setGeneration((current) => current + 1)
  }, [clearRetry])

  // Pause with the tab: a hidden tab must not hold a socket open or buffer into it.
  useEffect(() => {
    const sync = () => {
      const nowHidden = isHiddenRef.current()
      setHidden(nowHidden)
      if (!nowHidden) {
        // Coming back is a fresh start, not a continuation of an old backoff.
        attemptRef.current = 0
        setSocketState('connecting')
      }
    }
    document.addEventListener('visibilitychange', sync)
    return () => {
      document.removeEventListener('visibilitychange', sync)
    }
  }, [])

  useEffect(() => {
    if (hidden) {
      clearRetry()
      return undefined
    }

    let closed = false
    const source = factoryRef.current(path)

    const handleSnapshot = (event: MessageEvent<string>) => {
      const parsed = parseSnapshotFrame(event.data)
      if (!parsed) return
      attemptRef.current = 0
      setSocketState('live')
      setMeta(parsed.meta)
      setNotAvailableReason(parsed.reason)
      setSnapshot(parsed.snapshot)
      setUpdates((current) => current + 1)
      setLastFrameAt(Date.now())
      if (parsed.snapshot) {
        setEvents((current) => mergeEvents(current, parsed.snapshot?.events ?? []))
      }
    }

    const handleError = () => {
      if (closed) return
      closed = true
      source.close()
      const attempt = attemptRef.current
      attemptRef.current = attempt + 1
      setSocketState(attempt + 1 >= OFFLINE_AFTER_ATTEMPTS ? 'offline' : 'reconnecting')
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null
        setGeneration((current) => current + 1)
      }, backoffDelay(attempt))
    }

    source.addEventListener(SNAPSHOT_EVENT, handleSnapshot)
    source.addEventListener('error', handleError)

    return () => {
      closed = true
      clearRetry()
      source.close()
    }
  }, [hidden, generation, path, clearRetry])

  // Derived, not stored: a hidden tab is paused whatever the socket last was.
  const connection: LiveConnectionState = hidden ? 'paused' : socketState

  return {
    snapshot,
    meta,
    events,
    connection,
    updates,
    lastFrameAt,
    notAvailableReason,
    retryNow,
  }
}
