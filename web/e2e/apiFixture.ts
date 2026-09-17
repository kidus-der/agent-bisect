/**
 * Recorded responses from the real fixture API (`--fixture`, captured from
 * `/api/*`), replayed through `page.route`. The e2e suite owns its API: the
 * shapes and numbers are the server's, but the tests need neither a running
 * `bisect serve` nor the dev proxy.
 */
import { type Page } from '@playwright/test'

import fixtures from './fixtures/api.json' with { type: 'json' }

const META = { simulated: true, data_source: 'fixture' }

export const META_PAYLOAD = {
  ...META,
  package_version: '0.0.0-e2e',
  tau2_commit: 'e2e',
  agent_model: 'nvidia/llama-3.1-nemotron-70b-instruct',
  user_model: 'meta/llama-3.1-8b-instruct',
  generated_at: '2026-01-01T00:00:00Z',
}

/** Handy numbers the specs assert on, read off the recording rather than retyped. */
export const RECORDED = {
  headline: fixtures.overview.data.headline,
  kpis: fixtures.overview.data.kpis,
  heroRunId: fixtures.overview.data.hero_run.run_id,
  heroDecisiveStep: fixtures.overview.data.hero_run.decisive_step,
  runTotal: fixtures.runs.meta.total,
  runs: fixtures.runs.data.runs,
  /** First and last by the default `run_id` ascending sort. */
  firstRunId: fixtures.runs.data.runs[0]?.run_id ?? '',
  lastRunId: fixtures.runs.data.runs[fixtures.runs.data.runs.length - 1]?.run_id ?? '',
} as const

function envelope(data: unknown, meta: Record<string, unknown> = {}): Record<string, unknown> {
  return { success: true, data, error: null, meta: { ...META, ...meta } }
}

function runsFor(url: URL): unknown {
  const params = url.searchParams
  if (params.get('status') === 'recording') return fixtures.runsRecording
  const limit = Number(params.get('limit') ?? '100')
  const all = fixtures.runs.data.runs
  const outcome = params.get('outcome')
  const domain = params.get('domain')
  const model = params.get('model')
  // The real server filters and sorts; the recording is replayed the same way.
  const filtered = all.filter(
    (run) =>
      (outcome === null || run.outcome === outcome) &&
      (domain === null || run.domain === domain) &&
      (model === null || run.model === model),
  )
  const sort = params.get('sort') ?? 'run_id'
  const descending = sort.startsWith('-')
  const field = descending ? sort.slice(1) : sort
  const sorted = [...filtered].sort((a, b) => {
    const left = a[field as keyof typeof a]
    const right = b[field as keyof typeof b]
    if (left === right) return 0
    if (left === null) return 1
    if (right === null) return -1
    const order = left < right ? -1 : 1
    return descending ? -order : order
  })
  return envelope({ runs: sorted.slice(0, limit) }, { total: sorted.length, page: 1, limit })
}

/** Routes every endpoint these pages read. Call it before `page.goto`. */
export async function mockApi(page: Page): Promise<void> {
  await page.route('**/api/meta', (route) => route.fulfill({ json: envelope(META_PAYLOAD) }))
  await page.route('**/api/overview', (route) => route.fulfill({ json: fixtures.overview }))
  await page.route('**/api/benchmark', (route) => route.fulfill({ json: fixtures.benchmark }))
  await page.route('**/api/runs/*/steps/*/intervention-diff', (route) =>
    route.fulfill({ json: fixtures.interventionDiff }),
  )
  await page.route('**/api/runs/*', (route) => route.fulfill({ json: fixtures.runDetail }))
  await page.route(
    (url) => url.pathname === '/api/runs',
    (route) => route.fulfill({ json: runsFor(new URL(route.request().url())) }),
  )
  await page.route(
    (url) => url.pathname === '/api/search',
    (route) => {
      const query = new URL(route.request().url()).searchParams.get('q') ?? ''
      const recorded = query.includes('recording')
        ? fixtures.searchRecording
        : fixtures.searchRefund
      return route.fulfill({ json: recorded })
    },
  )
}
