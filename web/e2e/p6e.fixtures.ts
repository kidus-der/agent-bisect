/**
 * The Benchmark / Live / PR-checks e2e suite owns its API: these are real
 * `--fixture` responses captured from `agent_bisect.server`, replayed by route.
 * Regenerate them by running the fixture server and re-dumping the same paths.
 *
 * `/api/live/snapshot` is regenerated per request by the real server, so a
 * captured copy is also what makes the Live assertions deterministic.
 */
import type { Page, Route } from '@playwright/test'

import responses from './p6e.fixtures.json' with { type: 'json' }

interface ResponseMeta {
  readonly simulated: boolean
  /** The client rejects an envelope whose meta is missing this. */
  readonly data_source: 'fixture' | 'real'
  readonly total: number | null
  readonly page: number | null
  readonly limit: number | null
  readonly next_cursor: string | null
}

interface Envelope {
  readonly success: boolean
  readonly data: unknown
  readonly error: unknown
  readonly meta: ResponseMeta
}

const REAL_META: ResponseMeta = {
  simulated: false,
  data_source: 'real',
  total: null,
  page: null,
  limit: null,
  next_cursor: null,
}

const byPath = responses as unknown as Record<string, Envelope>

export const META = byPath['/api/meta'] as Envelope
export const BENCHMARK = byPath['/api/benchmark'] as Envelope
export const DATASET = byPath['/api/dataset?page=1&limit=50'] as Envelope
const RAW_LIVE_SNAPSHOT = byPath['/api/live/snapshot'] as Envelope

interface CallsPoint {
  readonly ts: string
  readonly model: string
  readonly calls_per_minute: number
}

/**
 * The live line anchors its right edge on the browser's clock, so a captured
 * series would trail off into a flat tail that grows with the age of the
 * capture. Shifting the whole series so its last point is "now" keeps the shape
 * and the spacing exactly as captured.
 */
function rebaseToNow(envelope: Envelope): Envelope {
  const data = envelope.data as { calls_series?: CallsPoint[] } | null
  const series = data?.calls_series
  if (!data || !series || series.length === 0) return envelope
  const latest = Math.max(...series.map((point) => Date.parse(point.ts)))
  if (!Number.isFinite(latest)) return envelope
  const shift = Date.now() - latest
  return {
    ...envelope,
    data: {
      ...data,
      calls_series: series.map((point) => ({
        ...point,
        ts: new Date(Date.parse(point.ts) + shift).toISOString(),
      })),
    },
  }
}
export const PR_CHECKS = byPath['/api/pr-checks'] as Envelope
export const PR_CHECK_REGRESSION = byPath['/api/pr-checks/pr-check-00'] as Envelope
export const PR_CHECK_CLEAN = byPath['/api/pr-checks/pr-check-03'] as Envelope

export const NOT_AVAILABLE_REASON = 'no eval results yet (data/eval.parquet not found)'

export function notAvailable(reason = NOT_AVAILABLE_REASON): Envelope {
  return {
    success: true,
    data: { status: 'not_available', reason },
    error: null,
    meta: REAL_META,
  }
}

export const LIVE_SNAPSHOT = RAW_LIVE_SNAPSHOT

function json(route: Route, body: unknown): Promise<void> {
  return route.fulfill({ json: body })
}

/** One SSE body carrying `count` snapshot frames; the stream then ends. */
export function snapshotStream(count: number, envelope: Envelope = LIVE_SNAPSHOT): string {
  const snapshotData = envelope.data as { calls_series?: unknown[]; events?: unknown[] } | null
  if (!snapshotData?.calls_series) {
    return Array.from(
      { length: count },
      () => `event: snapshot\ndata: ${JSON.stringify(envelope)}\n\n`,
    ).join('')
  }
  return Array.from({ length: count }, (_, index) => {
    const events = [
      {
        ts: new Date(Date.now() + index * 1000).toISOString(),
        level: 'info',
        message: `simulated: stream frame ${index}`,
      },
    ]
    const frame = { ...envelope, data: { ...snapshotData, events } }
    return `event: snapshot\ndata: ${JSON.stringify(frame)}\n\n`
  }).join('')
}

export interface MockOptions {
  /** Answer the benchmark, dataset and pr-check endpoints with `not_available`. */
  readonly unmeasured?: boolean
  /** Number of `event: snapshot` frames the stream emits before ending. */
  readonly streamFrames?: number
}

const DEFAULT_STREAM_FRAMES = 3

/** Routes every endpoint these three pages read. Call in `beforeEach`. */
export async function mockP6eApi(page: Page, options: MockOptions = {}): Promise<void> {
  const { unmeasured = false, streamFrames = DEFAULT_STREAM_FRAMES } = options

  await page.route('**/api/meta', (route) => json(route, META))

  await page.route('**/api/live/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' },
      body: snapshotStream(
        streamFrames,
        unmeasured ? notAvailable('no call ledger yet') : rebaseToNow(LIVE_SNAPSHOT),
      ),
    }),
  )

  await page.route('**/api/live/snapshot*', (route) =>
    json(route, unmeasured ? notAvailable('no call ledger yet') : rebaseToNow(LIVE_SNAPSHOT)),
  )
  await page.route('**/api/benchmark*', (route) =>
    json(route, unmeasured ? notAvailable() : BENCHMARK),
  )
  await page.route('**/api/dataset*', (route) => json(route, unmeasured ? notAvailable() : DATASET))
  await page.route('**/api/pr-checks/pr-check-00*', (route) => json(route, PR_CHECK_REGRESSION))
  await page.route('**/api/pr-checks/pr-check-03*', (route) => json(route, PR_CHECK_CLEAN))
  await page.route('**/api/pr-checks*', (route) =>
    json(route, unmeasured ? notAvailable('no gate results yet') : PR_CHECKS),
  )
}

export const THEME_KEY = 'bisect.theme'

export async function useTheme(page: Page, theme: 'dark' | 'light'): Promise<void> {
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
    THEME_KEY,
    theme,
  ] as const)
}

/** Fails if the document scrolls sideways at the current viewport. */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}
