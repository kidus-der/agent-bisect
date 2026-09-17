import { createMemoryHistory } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { createAppRouter } from '@/app/router'
import { RouterProvider } from '@tanstack/react-router'

import type { RunDetail } from './api'
import { RunDetailHeader } from './RunDetailHeader'

const RUN = {
  run_id: 'brief-12-step',
  domain: 'airline',
  task_id: 'refund_after_cancellation',
  agent_model: 'nvidia/llama-3.1-nemotron-70b-instruct',
  user_model: 'meta/llama-3.1-8b-instruct',
  seed: 7,
  tau2_commit: 'abc',
  created_at: '2026-08-01T09:00:00Z',
  status: 'complete',
  outcome: 'fail',
  reward: 0,
  steps: [],
  planted_step: 7,
  fault_type: 'wrong_value',
  estimate: null,
  judge: null,
} as unknown as RunDetail

const VERDICT = { step: 7, effect: 0.875, low: 0.4743, high: 0.965 }

/** The header renders links, so it needs the router around it. */
function renderHeader(run: RunDetail | null): HTMLElement {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ['/runs/brief-12-step'] }))
  const { container } = render(
    <RouterProvider
      router={router}
      defaultComponent={() => (
        <RunDetailHeader
          runId="brief-12-step"
          run={run}
          verdict={run ? VERDICT : null}
          simulated={run !== null}
        />
      )}
    />,
  )
  return container
}

/** The three elements the Runs row morphs into. */
const MORPH_TARGETS = ['id', 'blame', 'status'] as const

describe('RunDetailHeader morph targets', () => {
  it('carries all three targets once the run has loaded', () => {
    // Arrange / Act
    const container = renderHeader(RUN)

    // Assert
    for (const target of MORPH_TARGETS) {
      expect(container.querySelectorAll(`[data-morph="${target}"]`)).toHaveLength(1)
    }
  })

  it('carries the same targets while the run is still loading', () => {
    // The Runs row unmounts on navigation: if the targets only appear once the
    // fetch resolves, the morph lands on nothing and nothing travels.
    const container = renderHeader(null)

    for (const target of MORPH_TARGETS) {
      expect(container.querySelectorAll(`[data-morph="${target}"]`)).toHaveLength(1)
    }
  })

  it('shows the run id from the route before the payload arrives', () => {
    renderHeader(null)

    expect(screen.getByRole('heading', { level: 1, name: 'brief-12-step' })).toBeInTheDocument()
  })

  it('does not claim an outcome or a blame it has not loaded', () => {
    renderHeader(null)

    expect(screen.queryByText('Fail')).not.toBeInTheDocument()
    expect(screen.queryByText(/\+0\.88|\+0\.87/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('run-simulated-flag')).not.toBeInTheDocument()
  })
})
