import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test } from 'vitest'

import { AccuracyHeatmap } from './AccuracyHeatmap'
import type { HeatmapCell } from './api'

const CELLS: readonly HeatmapCell[] = [
  { fault_type: 'missing_field', method: 'bisect', accuracy: 0.9565, n: 23 },
  { fault_type: 'missing_field', method: 'judge_step_by_step', accuracy: 0.7826, n: 23 },
  { fault_type: 'wrong_value', method: 'bisect', accuracy: 0.9167, n: 24 },
  { fault_type: 'wrong_value', method: 'judge_step_by_step', accuracy: 0.75, n: 24 },
]

describe('AccuracyHeatmap matrix', () => {
  test('prints the value in every cell', () => {
    // Arrange / Act
    const { container } = render(<AccuracyHeatmap cells={CELLS} />)
    const matrix = container.querySelector('[data-slot="accuracy-matrix"]')

    // Assert — one printed percentage per cell, rounded to a whole point.
    expect(matrix).not.toBeNull()
    const printed = [...(matrix?.querySelectorAll('span.num') ?? [])]
      .map((cell) => cell.textContent)
      .filter((text) => text?.endsWith('%'))
    expect(printed).toEqual(['96%', '78%', '92%', '75%'])
  })

  test('shows n for each fault type', () => {
    render(<AccuracyHeatmap cells={CELLS} />)
    expect(screen.getByText('n = 23')).toBeInTheDocument()
    expect(screen.getByText('n = 24')).toBeInTheDocument()
  })

  test('marks a cell with no measurement rather than drawing a zero', () => {
    // Arrange — wrong_value was never run against no_control.
    const sparse = [...CELLS, { ...CELLS[0], method: 'no_control' } as HeatmapCell]

    // Act
    render(<AccuracyHeatmap cells={sparse} />)

    // Assert
    expect(screen.getByText('n/a')).toBeInTheDocument()
  })
})

describe('AccuracyHeatmap table fallback', () => {
  test('keeps a full table in the DOM while the matrix is on screen', () => {
    // Act
    render(<AccuracyHeatmap cells={CELLS} />)

    // Assert — the coloured grid is decorative; the table is the accessible path.
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3)
  })

  test('carries the Wilson interval and n, which do not fit in a cell', () => {
    // Act
    render(<AccuracyHeatmap cells={CELLS} />)

    // Assert
    const table = screen.getByRole('table')
    expect(within(table).getByText(/\[79\.0%, 99\.2%\] n=23/)).toBeInTheDocument()
  })

  test('swaps the matrix for the table when the control is switched', async () => {
    // Arrange
    const user = userEvent.setup()
    render(<AccuracyHeatmap cells={CELLS} />)
    expect(screen.getByText('n = 23')).toBeInTheDocument()

    // Act
    await user.click(screen.getByRole('radio', { name: 'Table' }))

    // Assert — the matrix is gone, the same numbers remain in the table.
    expect(screen.queryByText('n = 23')).not.toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('95.7%')).toBeInTheDocument()
  })

  test('names every method in full in the table header', () => {
    render(<AccuracyHeatmap cells={CELLS} />)
    const table = screen.getByRole('table')
    expect(within(table).getByRole('columnheader', { name: 'Bisect' })).toBeInTheDocument()
    expect(
      within(table).getByRole('columnheader', { name: 'Judge, step by step' }),
    ).toBeInTheDocument()
  })
})
