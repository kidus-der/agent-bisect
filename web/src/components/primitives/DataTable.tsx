import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { type ReactNode, useMemo, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

import { type SortState, type SortValue, nextSortState, sortRows } from './dataTableSort'

export interface DataTableColumn<Row> {
  readonly id: string
  readonly header: string
  readonly cell: (row: Row) => ReactNode
  /** Makes the column sortable. Return null for "not measured". */
  readonly sortValue?: (row: Row) => SortValue
  /** Right-aligned, tabular numerals. */
  readonly numeric?: boolean
  readonly width?: string
  /** Hide the column under the nav-collapse breakpoint. */
  readonly hideOnMobile?: boolean
}

interface DataTableProps<Row> {
  readonly columns: ReadonlyArray<DataTableColumn<Row>>
  readonly rows: readonly Row[]
  readonly getRowId: (row: Row) => string
  /** Accessible table name. */
  readonly caption: string
  readonly initialSort?: SortState
  readonly onRowActivate?: (row: Row) => void
  /** Set to scroll inside the table and virtualize rows. */
  readonly maxHeight?: number
  readonly rowHeight?: number
  readonly className?: string
}

const DEFAULT_ROW_HEIGHT = 44
const OVERSCAN_ROWS = 8
const HEADER_ROWS = 1

const ARIA_SORT = { asc: 'ascending', desc: 'descending' } as const

interface HeaderCellProps<Row> {
  readonly column: DataTableColumn<Row>
  readonly sort: SortState | null
  readonly onSort: (columnId: string) => void
}

function HeaderCell<Row>({ column, sort, onSort }: HeaderCellProps<Row>) {
  const direction = sort?.columnId === column.id ? sort.direction : undefined
  const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ChevronsUpDown
  return (
    <th
      scope="col"
      aria-sort={direction ? ARIA_SORT[direction] : undefined}
      style={column.width ? { width: column.width } : undefined}
      className={cn(
        'sticky top-0 z-(--z-sticky) h-9 border-b border-line bg-surface px-3 label-instrument font-medium whitespace-nowrap',
        column.numeric ? 'text-right' : 'text-left',
        column.hideOnMobile && 'hidden md:table-cell',
      )}
    >
      {column.sortValue ? (
        <button
          type="button"
          onClick={() => onSort(column.id)}
          className={cn(
            '-mx-1 inline-flex h-7 cursor-pointer items-center gap-1 rounded-step px-1 uppercase hover:text-ink',
            direction && 'text-ink',
          )}
        >
          {column.header}
          <Icon aria-hidden="true" className={cn('size-3', !direction && 'opacity-60')} />
        </button>
      ) : (
        column.header
      )}
    </th>
  )
}

interface BodyRowProps<Row> {
  readonly row: Row
  readonly columns: ReadonlyArray<DataTableColumn<Row>>
  readonly rowHeight: number
  /** 1-based position in the full (sorted) table, header included; required when virtualized. */
  readonly rowIndex: number
  readonly onRowActivate?: (row: Row) => void
}

const ACTIVATION_KEYS = ['Enter', ' ']

function BodyRow<Row>({ row, columns, rowHeight, rowIndex, onRowActivate }: BodyRowProps<Row>) {
  return (
    <tr
      aria-rowindex={rowIndex}
      tabIndex={onRowActivate ? 0 : undefined}
      onClick={onRowActivate ? () => onRowActivate(row) : undefined}
      onKeyDown={
        onRowActivate
          ? (event) => {
              if (!ACTIVATION_KEYS.includes(event.key) || event.target !== event.currentTarget)
                return
              // Space would otherwise scroll the table.
              event.preventDefault()
              onRowActivate(row)
            }
          : undefined
      }
      style={{ height: rowHeight }}
      className={cn(
        'border-b border-line last:border-b-0 hover:bg-elevated',
        onRowActivate && 'cursor-pointer focus-visible:-outline-offset-2',
      )}
    >
      {columns.map((column) => (
        <td
          key={column.id}
          className={cn(
            'px-3 text-small whitespace-nowrap',
            column.numeric && 'text-right num',
            column.hideOnMobile && 'hidden md:table-cell',
          )}
        >
          {column.cell(row)}
        </td>
      ))}
    </tr>
  )
}

interface SpacerRowProps {
  readonly height: number
  readonly span: number
}

function SpacerRow({ height, span }: SpacerRowProps) {
  if (height <= 0) return null
  return (
    <tr aria-hidden="true">
      <td colSpan={span} style={{ height, padding: 0 }} />
    </tr>
  )
}

/** Dense table base: sortable headers, sticky header, tabular numerals, optional virtualization. */
export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  caption,
  initialSort,
  onRowActivate,
  maxHeight,
  rowHeight = DEFAULT_ROW_HEIGHT,
  className,
}: DataTableProps<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const sortedRows = useMemo(() => {
    const column = columns.find((candidate) => candidate.id === sort?.columnId)
    return sortRows(rows, column?.sortValue, sort?.direction)
  }, [columns, rows, sort])

  const virtualized = maxHeight !== undefined
  // eslint-disable-next-line react-hooks/incompatible-library -- no React Compiler here; the virtualizer is read during render on purpose
  const virtualizer = useVirtualizer({
    count: sortedRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: OVERSCAN_ROWS,
    enabled: virtualized,
    initialRect: { width: 0, height: maxHeight ?? 0 },
  })

  const virtualItems = virtualized ? virtualizer.getVirtualItems() : []
  const firstItem = virtualItems[0]
  const lastItem = virtualItems[virtualItems.length - 1]
  const padTop = firstItem ? firstItem.start : 0
  const padBottom = lastItem ? virtualizer.getTotalSize() - lastItem.end : 0
  // Header is row 1, so body row i (0-based) is aria-rowindex i + 2.
  const visibleRows = virtualized
    ? virtualItems.flatMap((item) => {
        const row = sortedRows[item.index]
        return row === undefined ? [] : [{ row, rowIndex: item.index + HEADER_ROWS + 1 }]
      })
    : sortedRows.map((row, index) => ({ row, rowIndex: index + HEADER_ROWS + 1 }))

  return (
    <div
      ref={scrollRef}
      // A scrollable region must be reachable by keyboard.
      tabIndex={virtualized ? 0 : undefined}
      role={virtualized ? 'group' : undefined}
      aria-label={virtualized ? `${caption} (scrollable)` : undefined}
      style={virtualized ? { maxHeight } : undefined}
      className={cn('min-w-0 overflow-auto', className)}
    >
      <table
        aria-rowcount={sortedRows.length + HEADER_ROWS}
        className="w-full border-separate border-spacing-0"
      >
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr aria-rowindex={1}>
            {columns.map((column) => (
              <HeaderCell
                key={column.id}
                column={column}
                sort={sort}
                onSort={(columnId) => setSort((current) => nextSortState(current, columnId))}
              />
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:border-b [&_td]:border-line [&_tr:last-child_td]:border-b-0">
          <SpacerRow height={padTop} span={columns.length} />
          {visibleRows.map(({ row, rowIndex }) => (
            <BodyRow
              key={getRowId(row)}
              row={row}
              rowIndex={rowIndex}
              columns={columns}
              rowHeight={rowHeight}
              onRowActivate={onRowActivate}
            />
          ))}
          <SpacerRow height={padBottom} span={columns.length} />
        </tbody>
      </table>
    </div>
  )
}
