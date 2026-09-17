import type { UseQueryResult } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { ApiError, type ApiResult, type ResponseMeta } from '@/api/client'
import type { NotAvailable } from '@/api/payload'

import { AsyncSection } from './AsyncSection'

interface Payload {
  readonly accuracy: number
}

const META: ResponseMeta = {
  simulated: true,
  data_source: 'fixture',
  total: null,
  page: null,
  limit: null,
  next_cursor: null,
}

type Query = UseQueryResult<ApiResult<Payload | NotAvailable>, ApiError>

function query(overrides: Partial<Query>): Query {
  return {
    isPending: false,
    isError: false,
    data: undefined,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as Query
}

function renderSection(state: Query) {
  return render(
    <AsyncSection<Payload>
      query={state}
      subject="benchmark results"
      skeleton={<div data-slot="skeleton" />}
      notMeasured={{
        label: 'benchmark',
        title: 'No evaluation has been run',
        command: 'bisect eval',
      }}
    >
      {(payload) => <p>accuracy {payload.accuracy}</p>}
    </AsyncSection>,
  )
}

describe('AsyncSection', () => {
  test('announces what is loading while the request is in flight', () => {
    renderSection(query({ isPending: true }))
    expect(screen.getByRole('status')).toHaveTextContent('Loading benchmark results')
  })

  test('shows the error and its code, with a retry', async () => {
    // Arrange
    const refetch = vi.fn()
    const state = query({
      isError: true,
      error: new ApiError({ kind: 'network', code: 'network_error', message: 'Cannot reach it.' }),
      refetch,
    })

    // Act
    const user = userEvent.setup()
    renderSection(state)
    await user.click(screen.getByRole('button', { name: /retry/i }))

    // Assert
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach it.')
    expect(screen.getByText(/network_error/)).toBeInTheDocument()
    expect(refetch).toHaveBeenCalledOnce()
  })

  test('renders the payload once it arrives', () => {
    renderSection(query({ data: { data: { accuracy: 0.96 }, meta: META } }))
    expect(screen.getByText('accuracy 0.96')).toBeInTheDocument()
  })
})

describe('AsyncSection not_available', () => {
  const notAvailable = query({
    data: {
      data: {
        status: 'not_available',
        reason: 'no eval results yet (data/eval.parquet not found)',
      },
      meta: META,
    },
  })

  test('draws no numbers when the server says it has not measured', () => {
    renderSection(notAvailable)
    expect(screen.queryByText(/accuracy/)).not.toBeInTheDocument()
  })

  test('shows the server’s own reason verbatim', () => {
    renderSection(notAvailable)
    expect(
      screen.getByText('no eval results yet (data/eval.parquet not found)'),
    ).toBeInTheDocument()
  })

  test('says plainly that it is not measured, and how to measure it', () => {
    renderSection(notAvailable)
    expect(screen.getByText(/benchmark · not measured/i)).toBeInTheDocument()
    expect(screen.getByText('bisect eval')).toBeInTheDocument()
  })

  test('is not reported as an error', () => {
    renderSection(notAvailable)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
