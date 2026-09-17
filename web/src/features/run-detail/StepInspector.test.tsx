import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { StepView } from './api'
import { StepInspector } from './StepInspector'

const STEP: StepView = {
  step_idx: 7,
  actor: 'tool',
  tool_name: 'book_reservation',
  text: 'book_reservation returned',
  from_tape: true,
  state_changed: true,
}

const META = { simulated: true, data_source: 'fixture' }

const PAYLOAD = {
  step_idx: 7,
  messages: [{ role: 'tool', content: 'book_reservation returned' }],
  tool_args: { id: 'X0X2K6' },
  tool_result: { reservation_id: 'NM1VX1' },
}

type Fails = 'intervention-diff' | null

/** Every endpoint answers except the one under test, which refuses the connection. */
function stubApi(fails: Fails): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string) => {
      if (fails !== null && input.includes(fails)) {
        return Promise.reject(new TypeError('Failed to fetch'))
      }
      const data = input.includes('intervention-diff')
        ? null
        : input.includes('state-diff')
          ? { step_idx: 7, entries: [] }
          : PAYLOAD
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data, error: null, meta: META }),
      })
    }),
  )
}

function renderInspector(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <StepInspector runId="brief-12-step" step={STEP} stepIdx={7} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('StepInspector error handling', () => {
  it('says the intervention diff failed rather than "never intervened on"', async () => {
    // Arrange
    stubApi('intervention-diff')
    renderInspector()

    // Act
    await userEvent.click(await screen.findByRole('tab', { name: 'Intervention' }))

    // Assert: a fetch failure must never read as a fact about the run.
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the Bisect server')
    expect(screen.queryByText(/was never intervened on/)).not.toBeInTheDocument()
  })

  it('offers a retry that refetches the failed diff', async () => {
    stubApi('intervention-diff')
    renderInspector()
    await userEvent.click(await screen.findByRole('tab', { name: 'Intervention' }))
    await screen.findByRole('alert')

    // Act: the endpoint recovers, the user retries.
    stubApi(null)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText(/was never intervened on/)).toBeInTheDocument()
  })

  it('still reports "never intervened on" when the server really answers null', async () => {
    stubApi(null)
    renderInspector()

    await userEvent.click(await screen.findByRole('tab', { name: 'Intervention' }))

    expect(await screen.findByText(/was never intervened on/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
