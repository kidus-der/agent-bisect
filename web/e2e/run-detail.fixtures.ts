/**
 * The e2e suite owns its API: these are real `--fixture` responses captured from
 * `agent_bisect.server`, replayed by route. Regenerate them by running the
 * fixture server and re-dumping the same paths.
 */
import type { Page, Route } from '@playwright/test'

import responses from './run-detail.fixtures.json' with { type: 'json' }

export const BRIEF_RUN = 'brief-12-step'
export const EDGE_60_STEP = 'run-edge-60-step'

const RERUNS_PER_ARM = 16
const CONTROL_STEP = 1

const META = {
  simulated: true,
  data_source: 'fixture',
  total: null,
  page: null,
  limit: null,
  next_cursor: null,
} as const

type Envelope = { readonly success: boolean; readonly data: unknown }
const byPath = responses as Record<string, Envelope>

interface RerunRow {
  readonly rerun_id: string
  readonly arm: 'treated' | 'control'
  readonly step: number
  readonly seed: number
  readonly passed: boolean
  readonly n_steps: number
  readonly calls: number
}

interface StepEffect {
  readonly step: number
  readonly treated: { readonly successes: number; readonly n: number }
}

/**
 * The 60-step run's 968 re-runs, rebuilt from its own effect rows rather than
 * committed as a 100 KB blob: the matrix is exercised at full volume.
 */
function sixtyStepReruns(): readonly RerunRow[] {
  const detail = byPath[`/api/runs/${EDGE_60_STEP}`]?.data as
    | { estimate: { step_effects: readonly StepEffect[] } | null; steps: readonly unknown[] }
    | undefined
  const effects = detail?.estimate?.step_effects ?? []
  const nSteps = detail?.steps.length ?? 60
  const arm = (
    prefix: string,
    armName: RerunRow['arm'],
    step: number,
    successes: number,
    total: number,
  ): readonly RerunRow[] =>
    Array.from({ length: total }, (_, index) => ({
      rerun_id: `${EDGE_60_STEP}-${prefix}${step}-${index}`,
      arm: armName,
      step,
      seed: 100 + index,
      passed: index < successes,
      n_steps: nSteps,
      calls: 10,
    }))

  const control = effects[0]
  return [
    ...arm('c', 'control', CONTROL_STEP, control ? control.treated.successes : 0, RERUNS_PER_ARM),
    ...effects.flatMap((effect) =>
      arm('t', 'treated', effect.step, effect.treated.successes, effect.treated.n),
    ),
  ]
}

/** Only real API calls, never `/src/api/...` module requests. */
const API_ROUTE = (url: URL): boolean => url.pathname.startsWith('/api/')

function envelope(data: unknown): string {
  return JSON.stringify({ success: true, data, error: null, meta: META })
}

function notFound(runId: string): string {
  return JSON.stringify({
    success: false,
    data: null,
    error: { code: 'not_found', message: `no run '${runId}'` },
    meta: META,
  })
}

/**
 * Replays the captured responses for every `/api/...` request the page makes.
 * Matched by pathname, not by glob: `**` + `/api/` would also swallow Vite's own
 * module requests for `src/api/*`.
 */
export async function mockRunDetailApi(page: Page): Promise<void> {
  const generated: Record<string, unknown> = {
    [`/api/runs/${EDGE_60_STEP}/reruns`]: { reruns: sixtyStepReruns() },
  }

  await page.route(API_ROUTE, (route: Route) => {
    const path = new URL(route.request().url()).pathname
    const captured = byPath[path]
    if (captured) return route.fulfill({ contentType: 'application/json', body: envelope(captured.data) })
    if (path in generated) {
      return route.fulfill({ contentType: 'application/json', body: envelope(generated[path]) })
    }
    if (path.startsWith('/api/runs/')) {
      const runId = path.split('/')[3] ?? ''
      return route.fulfill({ status: 404, contentType: 'application/json', body: notFound(runId) })
    }
    return route.fulfill({ contentType: 'application/json', body: envelope(null) })
  })
}
