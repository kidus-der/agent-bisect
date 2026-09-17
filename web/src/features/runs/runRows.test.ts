import { describe, expect, test } from 'vitest'

import type { RunSummary } from './api'
import { type RunsPageResult, narrowRuns, resultSummary, runFacets } from './runRows'
import { DEFAULT_RUNS_SEARCH, type RunsSearch } from './runsSearch'

function run(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_id: 'run-0000',
    domain: 'airline',
    task_id: 'duplicate_booking_cleanup',
    model: 'meta/llama-3.3-70b-instruct',
    status: 'complete',
    outcome: 'pass',
    n_steps: 27,
    decisive_step: null,
    fault_type: null,
    planted_step: null,
    cost_usd: 0.42,
    calls: 120,
    sparkline: [],
    blame_stripe: [],
    ...overrides,
  }
}

const META = { simulated: true, data_source: 'fixture', total: 3, page: 1, limit: 100 } as const

function page(runs: readonly RunSummary[], total = 3): RunsPageResult {
  return { data: { runs: [...runs] }, meta: { ...META, total, next_cursor: null } }
}

const RUNS = [
  run({ run_id: 'brief-12-step', task_id: 'refund_after_cancellation', fault_type: 'wrong_value' }),
  run({ run_id: 'run-0001', task_id: 'order_dup_investigation', fault_type: 'tool_error' }),
  run({ run_id: 'run-0002', task_id: 'refund_window', domain: 'retail', fault_type: null }),
]

describe('narrowRuns', () => {
  test('flattens every loaded page', () => {
    const narrowed = narrowRuns([page(RUNS.slice(0, 2)), page(RUNS.slice(2))], DEFAULT_RUNS_SEARCH)
    expect(narrowed.rows).toHaveLength(3)
    expect(narrowed.loaded).toBe(3)
    expect(narrowed.total).toBe(3)
  })

  test('matches free text against both the run id and the task id', () => {
    const byId = narrowRuns([page(RUNS)], { ...DEFAULT_RUNS_SEARCH, q: 'brief' })
    expect(byId.rows.map((entry) => entry.run_id)).toEqual(['brief-12-step'])

    const byTask = narrowRuns([page(RUNS)], { ...DEFAULT_RUNS_SEARCH, q: 'REFUND' })
    expect(byTask.rows.map((entry) => entry.run_id)).toEqual(['brief-12-step', 'run-0002'])
  })

  test('filters by fault type, which the endpoint has no parameter for', () => {
    const narrowed = narrowRuns([page(RUNS)], { ...DEFAULT_RUNS_SEARCH, fault: 'tool_error' })
    expect(narrowed.rows.map((entry) => entry.run_id)).toEqual(['run-0001'])
  })

  test('reports not_available instead of an empty list', () => {
    const unavailable: RunsPageResult = {
      data: { status: 'not_available', reason: 'no recordings yet' },
      meta: { ...META, total: null, next_cursor: null },
    }
    const narrowed = narrowRuns([unavailable], DEFAULT_RUNS_SEARCH)
    expect(narrowed.notAvailable).toBe(true)
    expect(narrowed.rows).toEqual([])
  })

  test('an empty page is not the same as an unavailable one', () => {
    expect(narrowRuns([page([], 0)], DEFAULT_RUNS_SEARCH).notAvailable).toBe(false)
  })
})

describe('runFacets', () => {
  test('offers only values the loaded runs actually have, sorted', () => {
    expect(runFacets([page(RUNS)])).toEqual({
      domains: ['airline', 'retail'],
      models: ['meta/llama-3.3-70b-instruct'],
    })
  })
})

describe('resultSummary', () => {
  const narrowed = (search: RunsSearch) => narrowRuns([page(RUNS)], search)

  test('counts against the server total when the server did all the filtering', () => {
    expect(resultSummary(narrowed(DEFAULT_RUNS_SEARCH), DEFAULT_RUNS_SEARCH, true)).toBe(
      '3 of 3 runs',
    )
  })

  test('says what it actually searched while pages are still arriving', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'refund' }
    expect(resultSummary(narrowed(search), search, false)).toBe('2 runs in the 3 loaded so far')
  })

  test('counts against the total once every page is in', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'refund' }
    expect(resultSummary(narrowed(search), search, true)).toBe('2 of 3 runs')
  })

  test('uses the singular for one run', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'brief' }
    expect(resultSummary(narrowed(search), search, true)).toBe('1 of 3 run')
  })
})
