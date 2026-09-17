import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StateDiffPanel } from './StateDiffPanel'

const META = { simulated: true, data_source: 'fixture' }
const DIFF = {
  step_idx: 7,
  entries: [{ path: 'user.membership', kind: 'changed', before: '21MM', after: 'U9JL' }],
}

function stubApi(fails: boolean, data: unknown = DIFF): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      fails
        ? Promise.reject(new TypeError('Failed to fetch'))
        : Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ success: true, data, error: null, meta: META }),
          }),
    ),
  )
}

function renderPanel(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <StateDiffPanel runId="brief-12-step" stepIdx={7} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('StateDiffPanel', () => {
  it('shows what the step changed', async () => {
    // Arrange / Act
    stubApi(false)
    renderPanel()

    // Assert
    expect(await screen.findByText('membership')).toBeInTheDocument()
    expect(screen.getByText(/0 added, 0 removed, 1 changed/)).toBeInTheDocument()
  })

  it('says the fetch failed rather than "not available"', async () => {
    stubApi(true)
    renderPanel()

    // A network failure is not a fact about the recording.
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the Bisect server')
    expect(screen.queryByText(/is not available from this recording/)).not.toBeInTheDocument()
  })

  it('retries the failed fetch', async () => {
    stubApi(true)
    renderPanel()
    await screen.findByRole('alert')

    stubApi(false)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('membership')).toBeInTheDocument()
  })

  it('reports a genuinely unavailable diff as unavailable', async () => {
    stubApi(false, { status: 'not_available', reason: 'no recordings yet' })
    renderPanel()

    expect(await screen.findByText(/is not available from this recording/)).toBeInTheDocument()
  })
})
