import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { CliCommand, CodeBlock } from './CodeBlock'
import { DataTable, type DataTableColumn } from './DataTable'
import { nextSortState, sortRows } from './dataTableSort'
import { DiffBlock } from './DiffBlock'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { JsonView } from './JsonView'
import { Panel } from './Panel'
import { SegmentedControl } from './SegmentedControl'
import { LoadingRegion, Skeleton } from './Skeleton'
import { Tabs } from './Tabs'
import { Tooltip, TooltipProvider } from './Tooltip'

interface Row {
  readonly id: string
  readonly cost: number | null
}

const ROWS: readonly Row[] = [
  { id: 'run-2', cost: 0.5 },
  { id: 'run-10', cost: null },
  { id: 'run-1', cost: 0.2 },
]

const COLUMNS: ReadonlyArray<DataTableColumn<Row>> = [
  { id: 'id', header: 'Run', cell: (row) => row.id, sortValue: (row) => row.id },
  {
    id: 'cost',
    header: 'Cost',
    numeric: true,
    cell: (row) => row.cost ?? 'n/a',
    sortValue: (row) => row.cost,
  },
]

function renderedIds(): readonly string[] {
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell')[0]?.textContent ?? '')
}

describe('sortRows / nextSortState', () => {
  test('cycles asc -> desc -> unsorted, and restarts on another column', () => {
    const asc = nextSortState(null, 'cost')
    expect(asc).toEqual({ columnId: 'cost', direction: 'asc' })
    const desc = nextSortState(asc, 'cost')
    expect(desc).toEqual({ columnId: 'cost', direction: 'desc' })
    expect(nextSortState(desc, 'cost')).toBeNull()
    expect(nextSortState(desc, 'id')).toEqual({ columnId: 'id', direction: 'asc' })
  })

  test('never mutates its input and sorts ids naturally', () => {
    const copy = [...ROWS]
    const sorted = sortRows(ROWS, (row) => row.id, 'asc')
    expect(sorted.map((row) => row.id)).toEqual(['run-1', 'run-2', 'run-10'])
    expect(ROWS).toEqual(copy)
  })

  test('"not measured" sorts last in both directions', () => {
    expect(sortRows(ROWS, (row) => row.cost, 'asc').map((row) => row.id)).toEqual([
      'run-1',
      'run-2',
      'run-10',
    ])
    expect(sortRows(ROWS, (row) => row.cost, 'desc').map((row) => row.id)).toEqual([
      'run-2',
      'run-1',
      'run-10',
    ])
  })
})

describe('DataTable', () => {
  test('renders a captioned table and sorts through its header buttons', async () => {
    render(<DataTable caption="Runs" columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} />)
    expect(screen.getByRole('table', { name: 'Runs' })).toBeInTheDocument()
    expect(renderedIds()).toEqual(['run-2', 'run-10', 'run-1'])

    const costHeader = screen.getByRole('columnheader', { name: /Cost/ })
    await userEvent.click(within(costHeader).getByRole('button'))
    expect(costHeader).toHaveAttribute('aria-sort', 'ascending')
    expect(renderedIds()).toEqual(['run-1', 'run-2', 'run-10'])

    await userEvent.click(within(costHeader).getByRole('button'))
    expect(costHeader).toHaveAttribute('aria-sort', 'descending')
    await userEvent.click(within(costHeader).getByRole('button'))
    expect(costHeader).not.toHaveAttribute('aria-sort')
  })

  test('numeric columns are right-aligned tabular numerals', () => {
    render(<DataTable caption="Runs" columns={COLUMNS} rows={ROWS} getRowId={(row) => row.id} />)
    expect(screen.getByText('0.5')).toHaveClass('num', 'text-right')
    // Header is row 1; positions stay truthful when only a window of rows is mounted.
    expect(screen.getAllByRole('row').map((row) => row.getAttribute('aria-rowindex'))).toEqual([
      '1',
      '2',
      '3',
      '4',
    ])
  })

  test('rows activate by click, Enter and Space', async () => {
    const onRowActivate = vi.fn()
    render(
      <DataTable
        caption="Runs"
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        onRowActivate={onRowActivate}
      />,
    )
    const firstRow = screen.getAllByRole('row')[1]
    if (!firstRow) throw new Error('expected a body row')
    await userEvent.click(firstRow)
    firstRow.focus()
    await userEvent.keyboard('{Enter}')
    await userEvent.keyboard(' ')
    expect(onRowActivate).toHaveBeenCalledTimes(3)
    expect(onRowActivate).toHaveBeenLastCalledWith(ROWS[0])
  })

  test('virtualized mode exposes the full row count and a focusable scroll region', () => {
    render(
      <DataTable
        caption="Runs"
        columns={COLUMNS}
        rows={ROWS}
        getRowId={(row) => row.id}
        maxHeight={200}
      />,
    )
    expect(screen.getByRole('table')).toHaveAttribute('aria-rowcount', '4')
    expect(screen.getAllByRole('row')[0]).toHaveAttribute('aria-rowindex', '1')
    expect(screen.getByRole('group', { name: 'Runs (scrollable)' })).toHaveAttribute(
      'tabindex',
      '0',
    )
  })
})

describe('code surfaces', () => {
  test('CodeBlock copies its code and announces the result', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<CodeBlock label="terminal" code="bisect doctor" />)
    await user.click(screen.getByRole('button', { name: 'Copy terminal' }))
    expect(writeText).toHaveBeenCalledWith('bisect doctor')
    expect(await screen.findByRole('button', { name: 'Copied terminal' })).toBeInTheDocument()
  })

  test('a denied clipboard is reported, not swallowed', async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
    render(<CliCommand command="bisect serve" />)
    await user.click(screen.getByRole('button', { name: 'Copy command' }))
    expect(await screen.findByRole('button', { name: 'Copy failed command' })).toBeInTheDocument()
  })

  test('JsonView pretty-prints nested values, including empty containers and null', () => {
    const { container } = render(
      <JsonView value={{ step: 7, tags: [], meta: {}, note: null, ok: true, ids: ['a'] }} />,
    )
    const text = container.querySelector('pre')?.textContent ?? ''
    expect(text).toContain('"step": 7')
    expect(text).toContain('"tags": []')
    expect(text).toContain('"meta": {}')
    expect(text).toContain('"note": null')
    expect(text).toContain('"ids": [\n    "a"\n  ]')
  })

  test('DiffBlock marks old and new with sign glyphs and semantic del/ins', () => {
    const { container } = render(<DiffBlock before="NM1VX1" after="ZFA04Y" label="intervention" />)
    expect(container.querySelector('del')?.textContent).toContain('−')
    expect(container.querySelector('ins')?.textContent).toContain('+')
    expect(screen.getByText('NM1VX1')).toBeInTheDocument()
    expect(screen.getByText('ZFA04Y')).toBeInTheDocument()
  })
})

describe('Panel', () => {
  test('each variant has its own radius, so cards are never identical', () => {
    const radiusOf = (variant: 'card' | 'kpi' | 'chart' | 'elevated'): string => {
      const { container, unmount } = render(<Panel variant={variant}>x</Panel>)
      const match = /rounded-\w+/.exec(container.firstElementChild?.className ?? '')
      unmount()
      return match?.[0] ?? ''
    }
    const radii = [radiusOf('card'), radiusOf('kpi'), radiusOf('chart'), radiusOf('elevated')]
    expect(new Set(radii).size).toBe(4)
  })

  test('KPI tiles recede from cards, so the light theme does not read as empty boxes', () => {
    const kpi = render(<Panel variant="kpi">x</Panel>)
    expect(kpi.container.firstElementChild).toHaveClass('bg-recessed', 'border-line-strong')
    const card = render(<Panel variant="card">x</Panel>)
    expect(card.container.firstElementChild).toHaveClass('bg-surface', 'border-line')
  })

  test('registration marks appear on the blueprint canvas only', () => {
    const canvas = render(
      <Panel variant="canvas" label="tape">
        x
      </Panel>,
    )
    expect(canvas.container.querySelectorAll('svg[aria-hidden="true"]')).toHaveLength(4)
    expect(canvas.container.firstElementChild).toHaveClass('blueprint-dots')
    const card = render(<Panel variant="card">x</Panel>)
    expect(card.container.querySelectorAll('svg')).toHaveLength(0)
  })
})

describe('states', () => {
  test('EmptyState shows the CLI command that produces the data', () => {
    render(
      <EmptyState
        label="no runs"
        title="The tape is empty"
        description="Record some."
        command="bisect record --domain airline --tasks 0-19"
      />,
    )
    expect(screen.getByRole('heading', { name: 'The tape is empty' })).toBeInTheDocument()
    expect(screen.getByText('bisect record --domain airline --tasks 0-19')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy command' })).toBeInTheDocument()
  })

  test('ErrorState is an alert with the message, the code and a working retry', async () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Cannot reach the server." code="network_error" onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the server.')
    expect(screen.getByRole('alert')).toHaveTextContent('network_error')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  test('skeletons are hidden from assistive tech; the region announces what is loading', () => {
    const { container } = render(
      <LoadingRegion subject="runs">
        <Skeleton className="h-3" />
      </LoadingRegion>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Loading runs')
    expect(container.querySelector('.skeleton-shimmer')).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('LoadingRegion retry notice', () => {
  test('says nothing about retries on the first attempt', () => {
    render(
      <LoadingRegion subject="runs">
        <Skeleton className="h-3" />
      </LoadingRegion>,
    )
    expect(screen.queryByText(/retrying/)).toBeNull()
  })

  test('after a failed attempt it shows which attempt is running and why the last one failed', () => {
    render(
      <LoadingRegion
        subject="runs"
        failureCount={1}
        failureMessage="Cannot reach the Bisect server."
      >
        <Skeleton className="h-3" />
      </LoadingRegion>,
    )
    expect(screen.getByText('retrying… (2 of 3)')).toBeInTheDocument()
    expect(screen.getByText('Cannot reach the Bisect server.')).toBeInTheDocument()
  })

  test('never counts past the last attempt', () => {
    render(
      <LoadingRegion subject="runs" failureCount={7}>
        <Skeleton className="h-3" />
      </LoadingRegion>,
    )
    expect(screen.getByText('retrying… (3 of 3)')).toBeInTheDocument()
  })
})

describe('controls', () => {
  test('SegmentedControl is a labelled radio group', async () => {
    const onChange = vi.fn()
    render(
      <SegmentedControl
        label="Arm"
        value="treated"
        onChange={onChange}
        options={[
          { value: 'treated', label: 'Treated' },
          { value: 'control', label: 'Control' },
        ]}
      />,
    )
    expect(screen.getByRole('group', { name: 'Arm' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Treated' })).toBeChecked()
    await userEvent.click(screen.getByRole('radio', { name: 'Control' }))
    expect(onChange).toHaveBeenCalledWith('control')
  })

  test('Tabs switch with the arrow keys', async () => {
    render(
      <Tabs
        label="Inspector"
        items={[
          { value: 'a', label: 'Payload', content: <p>payload body</p> },
          { value: 'b', label: 'Diff', content: <p>diff body</p> },
        ]}
      />,
    )
    expect(screen.getByText('payload body')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Payload' }))
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Diff' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('diff body')).toBeInTheDocument()
  })

  test('Tooltip content appears on keyboard focus', async () => {
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip content="the threshold">
          <button type="button">δ</button>
        </Tooltip>
      </TooltipProvider>,
    )
    await userEvent.tab()
    expect(await screen.findByRole('tooltip')).toHaveTextContent('the threshold')
  })
})
