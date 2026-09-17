import { describe, expect, test } from 'vitest'

import { MIN_SEARCH_CHARS, type SearchResults, runHits } from './search'

const RESULTS: SearchResults = {
  query: 're',
  hits: [
    {
      kind: 'run',
      id: 'brief-12-step',
      title: 'brief-12-step',
      subtitle: 'airline · refund_after_cancellation',
      href: '/runs/brief-12-step',
      status: 'complete',
    },
    {
      kind: 'run',
      id: 'run-edge-recording-1',
      title: 'run-edge-recording-1',
      subtitle: 'airline · seat_upgrade_request',
      href: '/runs/run-edge-recording-1',
      status: 'recording',
    },
    { kind: 'page', id: 'runs', title: 'Runs', href: '/runs' },
  ],
}

describe('runHits', () => {
  test('keeps runs and drops the static page hits', () => {
    expect(runHits(RESULTS).map((hit) => hit.id)).toEqual(['brief-12-step', 'run-edge-recording-1'])
  })

  test('keeps a recording run, with its status, rather than hiding it', () => {
    expect(runHits(RESULTS)[1]?.status).toBe('recording')
  })

  test('is empty before any response has arrived', () => {
    expect(runHits(undefined)).toEqual([])
  })
})

describe('MIN_SEARCH_CHARS', () => {
  test('is above one, so a single keystroke does not query the whole corpus', () => {
    expect(MIN_SEARCH_CHARS).toBeGreaterThan(1)
  })
})
