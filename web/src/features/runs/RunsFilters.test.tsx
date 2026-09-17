import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { RunsFilters } from './RunsFilters'
import type { RunFacets } from './runRows'
import { DEFAULT_RUNS_SEARCH, type RunsSearch } from './runsSearch'

const FACETS: RunFacets = {
  domains: ['airline', 'retail'],
  models: ['meta/llama-3.3-70b-instruct', 'nvidia/llama-3.1-nemotron-70b-instruct'],
}

function setup(search: RunsSearch = DEFAULT_RUNS_SEARCH) {
  const onChange = vi.fn()
  render(
    <RunsFilters search={search} facets={FACETS} onChange={onChange} summary="266 of 266 runs" />,
  )
  return { onChange, user: userEvent.setup() }
}

describe('RunsFilters', () => {
  test('reports the result count', () => {
    setup()
    expect(screen.getByText('266 of 266 runs')).toBeInTheDocument()
  })

  test('selects a domain from the values the loaded runs actually have', async () => {
    const { onChange, user } = setup()
    await user.click(screen.getByRole('button', { name: 'retail' }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RUNS_SEARCH, domain: 'retail' })
  })

  test('pressing the active chip clears that filter', async () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, domain: 'retail' }
    const { onChange, user } = setup(search)
    await user.click(screen.getByRole('button', { name: 'retail' }))
    expect(onChange).toHaveBeenCalledWith({ ...search, domain: null })
  })

  test('filters by outcome through the segmented control', async () => {
    const { onChange, user } = setup()
    await user.click(screen.getByRole('radio', { name: '✕ Fail' }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RUNS_SEARCH, outcome: 'fail' })
  })

  test('filters by fault type, shown in words', async () => {
    const { onChange, user } = setup()
    await user.click(screen.getByRole('button', { name: 'stale record' }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RUNS_SEARCH, fault: 'stale_record' })
  })

  test('debounces the search field instead of navigating on every keystroke', async () => {
    const { onChange, user } = setup()
    await user.type(screen.getByRole('searchbox', { name: /search runs/i }), 'refund')
    expect(onChange).not.toHaveBeenCalled()
    expect(await screen.findByDisplayValue('refund')).toBeInTheDocument()
    await vi.waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RUNS_SEARCH, q: 'refund' }),
    )
  })

  test('offers no clear action when nothing is filtered', () => {
    setup()
    expect(screen.queryByRole('button', { name: /clear filters/i })).toBeNull()
  })

  test('clears every filter but keeps the chosen sort', async () => {
    const search: RunsSearch = { ...DEFAULT_RUNS_SEARCH, q: 'a', fault: 'tool_error', sort: 'calls' }
    const { onChange, user } = setup(search)
    await user.click(screen.getByRole('button', { name: /clear filters/i }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RUNS_SEARCH, sort: 'calls', dir: 'asc' })
  })
})
