import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { stubMatchMedia } from '@/test/setup'

import { DataTable, type DataTableColumn } from './DataTable'

interface Run {
  readonly id: string
  readonly steps: number
}

const ROWS: readonly Run[] = [
  { id: 'run-003', steps: 12 },
  { id: 'run-001', steps: 40 },
  { id: 'run-002', steps: 7 },
]

const COLUMNS: ReadonlyArray<DataTableColumn<Run>> = [
  { id: 'id', header: 'Run', cell: (row) => row.id, sortValue: (row) => row.id },
  { id: 'steps', header: 'Steps', cell: (row) => row.steps, numeric: true, sortValue: (row) => row.steps },
]

const WIDE = '(min-width: 768px)'

function rowIds(): readonly string[] {
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell')[0]?.textContent ?? '')
}

afterEach(() => stubMatchMedia(() => false))

describe('DataTable sorting', () => {
  test('sorts rows itself when no sort handler is given', async () => {
    stubMatchMedia((query) => query === WIDE)
    const user = userEvent.setup()
    render(<DataTable columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} caption="Runs" />)

    await user.click(screen.getByRole('button', { name: /Run/ }))
    expect(rowIds()).toEqual(['run-001', 'run-002', 'run-003'])
  })

  test('leaves a controlled table in the order it was given', async () => {
    stubMatchMedia((query) => query === WIDE)
    const onSortChange = vi.fn()
    const user = userEvent.setup()
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        caption="Runs"
        sort={{ columnId: 'steps', direction: 'desc' }}
        onSortChange={onSortChange}
      />,
    )

    expect(rowIds()).toEqual(['run-003', 'run-001', 'run-002'])
    await user.click(screen.getByRole('button', { name: /Steps/ }))
    expect(onSortChange).toHaveBeenCalledWith('steps')
    // The owner decides what happens next; the table did not reorder anything.
    expect(rowIds()).toEqual(['run-003', 'run-001', 'run-002'])
  })

  test('announces the controlled sort direction on the right column', () => {
    stubMatchMedia((query) => query === WIDE)
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        caption="Runs"
        sort={{ columnId: 'steps', direction: 'desc' }}
        onSortChange={vi.fn()}
      />,
    )
    expect(screen.getByRole('columnheader', { name: /Steps/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
    expect(screen.getByRole('columnheader', { name: /Run/ })).not.toHaveAttribute('aria-sort')
  })
})

describe('DataTable row activation', () => {
  test('opens a row with Enter from the keyboard', async () => {
    stubMatchMedia((query) => query === WIDE)
    const onRowActivate = vi.fn()
    const user = userEvent.setup()
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        caption="Runs"
        onRowActivate={onRowActivate}
      />,
    )
    // Two sortable headers come first in the tab order, then the first row.
    await user.tab()
    await user.tab()
    await user.tab()
    expect(screen.getAllByRole('row')[1]).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onRowActivate).toHaveBeenCalledWith(ROWS[0])
  })
})

describe('DataTable compact layout', () => {
  test('becomes a list below the breakpoint instead of scrolling sideways', () => {
    stubMatchMedia(() => false)
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        caption="Runs"
        renderCompactRow={(row) => <span>{row.id} compact</span>}
      />,
    )
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByRole('list', { name: 'Runs' })).toBeInTheDocument()
    expect(screen.getByText('run-003 compact')).toBeInTheDocument()
  })

  test('stays a table above the breakpoint', () => {
    stubMatchMedia((query) => query === WIDE)
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        caption="Runs"
        renderCompactRow={(row) => <span>{row.id} compact</span>}
      />,
    )
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.queryByText('run-003 compact')).toBeNull()
  })

  test('keeps the table when no compact renderer was provided', () => {
    stubMatchMedia(() => false)
    render(<DataTable columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} caption="Runs" />)
    expect(screen.getByRole('table')).toBeInTheDocument()
  })
})
