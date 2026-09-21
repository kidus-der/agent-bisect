import { describe, expect, test } from 'vitest'

import { runsQueryString } from './api'
import {
  DEFAULT_RUNS_SEARCH,
  type RunsSearch,
  clearFilters,
  hasActiveFilters,
  nextSort,
  serverFilters,
  normaliseRunsSearch,
  toSearchParams,
  validateRunsSearch,
} from './runsSearch'

describe('validateRunsSearch', () => {
  test('reads a full view out of the URL', () => {
    expect(
      validateRunsSearch({
        q: 'refund',
        domain: 'airline',
        outcome: 'fail',
        status: 'complete',
        model: 'meta/llama-3.3-70b-instruct',
        fault: 'wrong_value',
        sort: 'n_steps',
        dir: 'desc',
        includeReruns: true,
      }),
    ).toEqual({
      q: 'refund',
      domain: 'airline',
      outcome: 'fail',
      status: 'complete',
      model: 'meta/llama-3.3-70b-instruct',
      fault: 'wrong_value',
      sort: 'n_steps',
      dir: 'desc',
      includeReruns: true,
    })
  })

  test('falls back to defaults for an empty URL', () => {
    expect(validateRunsSearch({})).toEqual(DEFAULT_RUNS_SEARCH)
  })

  test('rejects values the API would not accept rather than forwarding them', () => {
    const parsed = validateRunsSearch({
      outcome: 'maybe',
      status: 'deleted',
      fault: 'cosmic_ray',
      sort: 'cost_usd; DROP TABLE',
      dir: 'sideways',
    })
    expect(parsed).toMatchObject({
      outcome: null,
      status: null,
      fault: null,
      sort: 'run_id',
      dir: 'asc',
    })
  })

  test('caps a long query at the length the route accepts, so it is never a 422', () => {
    expect(validateRunsSearch({ q: 'x'.repeat(500) }).q).toHaveLength(100)
  })

  test('treats a blank filter as absent', () => {
    expect(validateRunsSearch({ domain: '   ' }).domain).toBeNull()
  })

  test('includeReruns defaults to false and only "true" turns it on', () => {
    expect(validateRunsSearch({}).includeReruns).toBe(false)
    expect(validateRunsSearch({ includeReruns: true }).includeReruns).toBe(true)
    expect(validateRunsSearch({ includeReruns: 'true' }).includeReruns).toBe(true)
    expect(validateRunsSearch({ includeReruns: 'nonsense' }).includeReruns).toBe(false)
  })
})

describe('toSearchParams', () => {
  test('omits defaults so a shared link carries only what was chosen', () => {
    expect(toSearchParams(DEFAULT_RUNS_SEARCH)).toEqual({})
  })

  test('round-trips a chosen view', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, domain: 'retail', outcome: 'fail' }
    expect(validateRunsSearch(toSearchParams(search))).toEqual(search)
  })

  test('includeReruns is only carried in the link when it is on', () => {
    expect(toSearchParams({ ...DEFAULT_RUNS_SEARCH, includeReruns: true })).toEqual({
      includeReruns: true,
    })
    expect(toSearchParams({ ...DEFAULT_RUNS_SEARCH, includeReruns: false })).toEqual({})
  })
})

describe('normaliseRunsSearch', () => {
  test('a bare /runs link keeps a bare URL', () => {
    expect(normaliseRunsSearch({})).toEqual({})
  })

  test('keeps what was chosen and drops what was not', () => {
    expect(normaliseRunsSearch({ outcome: 'fail', dir: 'asc', nonsense: 1 })).toEqual({
      outcome: 'fail',
    })
  })

  test('drops a value the API would reject rather than passing it through', () => {
    expect(normaliseRunsSearch({ outcome: 'maybe' })).toEqual({})
  })
})

describe('nextSort', () => {
  test('starts a new column ascending', () => {
    expect(nextSort(DEFAULT_RUNS_SEARCH, 'n_steps')).toMatchObject({
      sort: 'n_steps',
      dir: 'asc',
    })
  })

  test('flips the direction of the active column', () => {
    const once = nextSort(DEFAULT_RUNS_SEARCH, 'run_id')
    expect(once.dir).toBe('desc')
    expect(nextSort(once, 'run_id').dir).toBe('asc')
  })
})

describe('serverFilters and the query string', () => {
  test('sends every filter to the server, with the sign-prefixed sort', () => {
    const search: RunsSearch = {
      ...DEFAULT_RUNS_SEARCH,
      q: 'refund',
      fault: 'wrong_value',
      domain: 'airline',
      sort: 'cost_usd',
      dir: 'desc',
    }
    const query = runsQueryString(serverFilters(search), 2)
    expect(query).toContain('sort=-cost_usd')
    expect(query).toContain('domain=airline')
    expect(query).toContain('page=2')
    expect(query).toContain('q=refund')
    expect(query).toContain('fault_type=wrong_value')
  })

  test('omits a filter that was never chosen', () => {
    const query = runsQueryString(serverFilters(DEFAULT_RUNS_SEARCH), 1)
    expect(query).not.toContain('q=')
    expect(query).not.toContain('fault_type=')
  })

  test('selects unplanted runs with the server\u2019s own sentinel', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, fault: 'none' }
    expect(runsQueryString(serverFilters(search), 1)).toContain('fault_type=none')
  })

  test('never sends a query longer than the route accepts', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'x'.repeat(500) }
    const value = new URLSearchParams(runsQueryString(serverFilters(search), 1)).get('q')
    expect(value).toHaveLength(100)
  })

  test('includeReruns sends kind=all; off relies on the server default', () => {
    const on: RunsSearch = { ...DEFAULT_RUNS_SEARCH, includeReruns: true }
    expect(runsQueryString(serverFilters(on), 1)).toContain('kind=all')
    expect(runsQueryString(serverFilters(DEFAULT_RUNS_SEARCH), 1)).not.toContain('kind=')
  })
})

describe('hasActiveFilters / clearFilters', () => {
  test('sorting alone is not a filter', () => {
    expect(hasActiveFilters(nextSort(DEFAULT_RUNS_SEARCH, 'n_steps'))).toBe(false)
  })

  test('any narrowing counts, and clearing keeps the chosen sort', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, fault: 'tool_error', sort: 'calls' }
    expect(hasActiveFilters(search)).toBe(true)
    expect(clearFilters(search)).toEqual({ ...DEFAULT_RUNS_SEARCH, sort: 'calls', dir: 'asc' })
  })
})
