import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { RunPreview } from './RunPreview'
import { stripeCellWidth } from './stripeCellWidth'

const META = { simulated: true, data_source: 'fixture' }

function armResult(passes: number) {
  return { passes, n: 8, rate: passes / 8 }
}

function runPayload(overrides: Record<string, unknown>) {
  return {
    run_id: 'run-0016',
    status: 'complete',
    outcome: 'fail',
    steps: Array.from({ length: 12 }, (_, index) => ({ step: index + 1 })),
    estimate: {
      blamed_step: 7,
      step_effects: [
        {
          step: 5,
          effect: 0.12,
          ci_low: -0.1,
          ci_high: 0.35,
          treated: armResult(3),
          control: armResult(2),
        },
        {
          step: 7,
          effect: 0.75,
          ci_low: 0.41,
          ci_high: 0.94,
          treated: armResult(7),
          control: armResult(1),
        },
      ],
    },
    ...overrides,
  }
}

function mockRun(payload: unknown, ok = true): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({
        ok,
        status: ok ? 200 : 404,
        json: () =>
          Promise.resolve(
            ok
              ? { success: true, data: payload, error: null, meta: META }
              : {
                  success: false,
                  data: null,
                  error: { code: 'run_not_found', message: 'No such run.' },
                  meta: META,
                },
          ),
      }),
    ),
  )
}

function renderPreview(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RunPreview runId="run-0016" />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('RunPreview', () => {
  test('shows outcome glyph, step count, heat stripe and the blame chip with its interval', async () => {
    mockRun(runPayload({}))
    renderPreview()
    expect(await screen.findByText('Fail')).toBeInTheDocument()
    expect(screen.getByText('12 steps')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /12 steps, 2 tested, 10 untested/ })).toBeInTheDocument()
    expect(screen.getByText('+0.75')).toBeInTheDocument()
    expect(screen.getByText('[+0.41, +0.94]')).toBeInTheDocument()
  })

  test('a run that was never bisected says so and invents no blame', async () => {
    mockRun(runPayload({ estimate: null, outcome: 'pass' }))
    renderPreview()
    expect(await screen.findByText('Not bisected yet.')).toBeInTheDocument()
    expect(screen.queryByText(/step \d+/)).toBeNull()
  })

  test('a recording run has no outcome pill', async () => {
    mockRun(runPayload({ status: 'recording', outcome: null, estimate: null }))
    renderPreview()
    expect(await screen.findByText(/recording · no outcome yet/)).toBeInTheDocument()
    expect(screen.queryByText('Pass')).toBeNull()
    expect(screen.queryByText('Fail')).toBeNull()
  })

  test('a failed lookup degrades to a quiet line with the error code', async () => {
    mockRun(null, false)
    renderPreview()
    expect(await screen.findByText(/Preview unavailable/)).toHaveTextContent('run_not_found')
  })

  test('the stripe always fits the pane, from 12 to 60 steps', () => {
    expect(stripeCellWidth(12)).toBe(14)
    for (const steps of [12, 24, 60]) {
      const width = steps * (stripeCellWidth(steps) + 2) - 2
      expect(width).toBeLessThanOrEqual(256)
    }
    expect(stripeCellWidth(0)).toBe(14)
  })
})
