import { describe, expect, test } from 'vitest'

import type { JobStatus } from './api'
import { formatDuration, formatItems, jobFacts, shortModel } from './jobDetail'

function job(overrides: Partial<JobStatus> = {}): JobStatus {
  return {
    job_id: 'job-0',
    kind: 'blame',
    progress: 0.36,
    state: 'running',
    phase: 'P5',
    label: 'step-by-step blame search',
    items_done: 6,
    items_total: 16,
    model: 'nvidia/llama-3.1-nemotron-70b-instruct',
    calls_spent: 48,
    started_at: '2026-09-17T18:48:03Z',
    finished_at: null,
    eta_seconds: 426.7,
    last_checkpoint_at: '2026-09-17T18:52:03Z',
    error: null,
    ...overrides,
  } as JobStatus
}

describe('formatDuration', () => {
  test('reads seconds, minutes and hours', () => {
    expect(formatDuration(43)).toBe('43s')
    expect(formatDuration(426.7)).toBe('7m 07s')
    expect(formatDuration(4320)).toBe('1h 12m')
  })

  test('refuses to render a duration it cannot have', () => {
    expect(formatDuration(Number.NaN)).toBe('—')
    expect(formatDuration(-1)).toBe('—')
  })
})

describe('job facts', () => {
  test('counts items the server has counted', () => {
    expect(formatItems(job())).toBe('6 / 16')
  })

  test('reports an uncounted job as absent rather than as zero', () => {
    expect(formatItems(job({ items_done: null, items_total: null }))).toBeNull()
    expect(formatItems(job({ items_total: null }))).toBeNull()
  })

  test('trims the provider prefix off the model', () => {
    expect(shortModel(job())).toBe('llama-3.1-nemotron-70b-instruct')
    expect(shortModel(job({ model: null }))).toBeNull()
  })

  test('shows an ETA only while a job is running', () => {
    const running = jobFacts(job()).find((fact) => fact.label === 'eta')
    const queued = jobFacts(job({ state: 'queued' })).find((fact) => fact.label === 'eta')
    expect(running?.value).toBe('7m 07s')
    expect(queued?.value).toBeNull()
  })

  test('every fact a server has not measured is null, never invented', () => {
    // Arrange — the shape a real-mode server returns before it has counted.
    const bare = job({
      items_done: null,
      items_total: null,
      model: null,
      calls_spent: null,
      eta_seconds: null,
    })

    // Assert
    expect(jobFacts(bare).every((fact) => fact.value === null)).toBe(true)
  })
})
