import { describe, expect, test } from 'vitest'

import { runsQueryString } from './api'
import {
  DEFAULT_RUNS_SEARCH,
  type RunsSearch,
  clearFilters,
  hasActiveFilters,
  nextSort,
  serverFilters,
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

  test('caps a very long query so the URL cannot be used as a payload', () => {
    expect(validateRunsSearch({ q: 'x'.repeat(500) }).q).toHaveLength(120)
  })

  test('treats a blank filter as absent', () => {
    expect(validateRunsSearch({ domain: '   ' }).domain).toBeNull()
  })
})

describe('toSearchParams', () => {
  test('omits defaults so a shared link carries only what was chosen', () => {
    expect(toSearchParams(DEFAULT_RUNS_SEARCH)).toEqual({
      q: undefined,
      domain: undefined,
      outcome: undefined,
      status: undefined,
      model: undefined,
      fault: undefined,
      sort: undefined,
      dir: undefined,
    })
  })

  test('round-trips a chosen view', () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, domain: 'retail', outcome: 'fail' }
    expect(validateRunsSearch(toSearchParams(search))).toEqual(search)
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
  test('sends only parameters /api/runs accepts, with the sign-prefixed sort', () => {
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
    // Free text and fault type are not query parameters on this endpoint.
    expect(query).not.toContain('refund')
    expect(query).not.toContain('wrong_value')
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
