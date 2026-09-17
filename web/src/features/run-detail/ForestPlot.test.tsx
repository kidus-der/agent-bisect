import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { FALLBACK_DELTA, type ForestRow } from './blame'
import { ForestPlot } from './ForestPlot'

const ROWS: readonly ForestRow[] = [
  { step: 2, effect: 0.06, low: -0.2, high: 0.32, clears: false, blamed: false },
  { step: 7, effect: 0.88, low: 0.47, high: 0.97, clears: true, blamed: true },
  { step: 8, effect: 0.25, low: -0.05, high: 0.51, clears: false, blamed: false },
]

function renderPlot(onSelectStep = vi.fn(), selectedStep = 7) {
  render(
    <ForestPlot
      rows={ROWS}
      domain={[-0.4, 1]}
      delta={FALLBACK_DELTA}
      selectedStep={selectedStep}
      onSelectStep={onSelectStep}
    />,
  )
  return onSelectStep
}

describe('ForestPlot', () => {
  it('never announces an estimate without its interval', () => {
    // Arrange / Act
    renderPlot()

    // Assert
    expect(
      screen.getByRole('button', {
        name: 'Step 2, effect +0.06, 95% interval −0.20 to +0.32',
      }),
    ).toBeInTheDocument()
  })

  it('says which row is the earliest clearing step', () => {
    renderPlot()

    expect(
      screen.getByRole('button', {
        name: 'Step 7, effect +0.88, 95% interval +0.47 to +0.97, the earliest step clearing the threshold',
      }),
    ).toBeInTheDocument()
  })

  it('marks the selected row so the timeline and the plot agree', () => {
    renderPlot(vi.fn(), 8)

    expect(screen.getByRole('button', { name: /Step 8/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Step 7/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('selects a step by keyboard', async () => {
    const onSelectStep = renderPlot()
    const user = userEvent.setup()

    await user.tab()
    await user.keyboard('{Enter}')

    expect(onSelectStep).toHaveBeenCalledWith(2)
  })

  it('draws the blamed row a visible whisker like every other row', () => {
    // Arrange / Act: a gradient stroke on a zero-height line renders as nothing,
    // so the one row that most needs its interval lost it.
    const { container } = render(
      <ForestPlot
        rows={ROWS}
        domain={[-0.4, 1]}
        delta={FALLBACK_DELTA}
        selectedStep={7}
        onSelectStep={vi.fn()}
      />,
    )

    // Assert: every row has a whisker, and none is painted with a gradient url.
    const whiskers = container.querySelectorAll('[data-whisker]')
    expect(whiskers).toHaveLength(ROWS.length * 3)
    for (const whisker of whiskers) {
      expect(whisker.getAttribute('stroke')).not.toContain('url(')
    }
  })

  it('labels the threshold it is drawn against', () => {
    renderPlot()

    expect(screen.getByText('δ 0.10')).toBeInTheDocument()
  })

  it('offers the same numbers as a table for screen readers', () => {
    renderPlot()

    const table = screen.getByRole('table', {
      name: 'Per-step causal effect with its 95% confidence interval',
    })
    const blamedRow = within(table).getByRole('row', { name: /^7 /u })
    expect(within(blamedRow).getByRole('cell', { name: 'yes' })).toBeInTheDocument()
  })
})
