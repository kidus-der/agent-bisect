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

const META = { simulated: true, data_source: 'fixture', page: 1, limit: 100 } as const

function page(runs: readonly RunSummary[], total = runs.length): RunsPageResult {
  return { data: { runs: [...runs] }, meta: { ...META, total, next_cursor: null } }
}

const RUNS = [
  run({ run_id: 'brief-12-step', task_id: 'refund_after_cancellation', fault_type: 'wrong_value' }),
  run({ run_id: 'run-0001', task_id: 'order_dup_investigation', fault_type: 'tool_error' }),
  run({ run_id: 'run-0002', task_id: 'refund_window', domain: 'retail' }),
]

describe('narrowRuns', () => {
  test('flattens every loaded page without filtering anything itself', () => {
    const narrowed = narrowRuns([page(RUNS.slice(0, 2), 3), page(RUNS.slice(2), 3)])
    expect(narrowed.rows.map((entry) => entry.run_id)).toEqual([
      'brief-12-step',
      'run-0001',
      'run-0002',
    ])
    expect(narrowed.loaded).toBe(3)
  })

  test('takes the matching total from the latest page, not the rows in hand', () => {
    // The server counts after every filter, so one page of 2 can report 266.
    expect(narrowRuns([page(RUNS.slice(0, 2), 266)]).total).toBe(266)
  })

  test('reports not_available instead of an empty list', () => {
    const unavailable: RunsPageResult = {
      data: { status: 'not_available', reason: 'no recordings yet' },
      meta: { ...META, total: null, next_cursor: null },
    }
    const narrowed = narrowRuns([unavailable])
    expect(narrowed.notAvailable).toBe(true)
    expect(narrowed.rows).toEqual([])
  })

  test('an empty page is not the same as an unavailable one', () => {
    expect(narrowRuns([page([], 0)]).notAvailable).toBe(false)
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
  test('counts the whole corpus when nothing is filtered', () => {
    expect(resultSummary(narrowRuns([page(RUNS, 266)]), DEFAULT_RUNS_SEARCH)).toBe('266 runs')
  })

  test('says the count is a match when a filter is on', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'refund' }
    expect(resultSummary(narrowRuns([page(RUNS, 33)]), search)).toBe('33 runs match')
  })

  test('counts the matching total, not the page in hand', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, fault: 'tool_error' }
    expect(resultSummary(narrowRuns([page(RUNS.slice(0, 1), 21)]), search)).toBe('21 runs match')
  })

  test('uses the singular for one run', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'brief' }
    expect(resultSummary(narrowRuns([page(RUNS.slice(0, 1), 1)]), search)).toBe('1 run matches')
  })

  test('falls back to what is loaded when the server reports no total', () => {
    const noTotal: RunsPageResult = {
      data: { runs: [...RUNS] },
      meta: { ...META, total: null, next_cursor: null },
    }
    expect(resultSummary(narrowRuns([noTotal]), DEFAULT_RUNS_SEARCH)).toBe('3 runs')
  })
})
