import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { type ReactNode, useMemo, useRef, useState } from 'react'

import { springTransition } from '@/design/motion'
import { useMediaQuery } from '@/lib/useMediaQuery'
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
  /**
   * Controlled sort. Passing `onSortChange` hands sorting to the caller — the
   * table then reflects `sort` in the headers but leaves `rows` in the order it
   * was given, which is what a server-sorted list needs.
   */
  readonly sort?: SortState | null
  readonly onSortChange?: (columnId: string) => void
  readonly onRowActivate?: (row: Row) => void
  /** Set to scroll inside the table and virtualize rows. */
  readonly maxHeight?: number
  readonly rowHeight?: number
  /**
   * Below `--breakpoint-md` the table becomes this list instead of scrolling
   * sideways. Rows stay virtualized; only the row renderer changes.
   */
  readonly renderCompactRow?: (row: Row) => ReactNode
  readonly compactRowHeight?: number
  readonly className?: string
}

const DEFAULT_ROW_HEIGHT = 44
const DEFAULT_COMPACT_ROW_HEIGHT = 84
const OVERSCAN_ROWS = 8
const HEADER_ROWS = 1
const HOVER_LIFT_PX = 2
const PRESS_SCALE = 0.995
/** Matches `--breakpoint-md`, where the top nav collapses into the bottom tab bar. */
const WIDE_QUERY = '(min-width: 768px)'

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

/** Enter and Space activate a row; Space must not also scroll the table. */
function activationHandler<Row>(
  row: Row,
  onRowActivate: ((row: Row) => void) | undefined,
): ((event: React.KeyboardEvent) => void) | undefined {
  if (!onRowActivate) return undefined
  return (event) => {
    if (!ACTIVATION_KEYS.includes(event.key) || event.target !== event.currentTarget) return
    event.preventDefault()
    onRowActivate(row)
  }
}

function BodyRow<Row>({ row, columns, rowHeight, rowIndex, onRowActivate }: BodyRowProps<Row>) {
  const reduced = useReducedMotion() ?? false
  const interactive = onRowActivate !== undefined
  return (
    <motion.tr
      aria-rowindex={rowIndex}
      tabIndex={interactive ? 0 : undefined}
      onClick={onRowActivate ? () => onRowActivate(row) : undefined}
      onKeyDown={activationHandler(row, onRowActivate)}
      // Transform only: a lift must not reflow the virtualized list.
      whileHover={interactive && !reduced ? { y: -HOVER_LIFT_PX } : undefined}
      whileTap={interactive && !reduced ? { y: 0, scale: PRESS_SCALE } : undefined}
      transition={springTransition('settle', reduced)}
      style={{ height: rowHeight }}
      className={cn(
        'relative border-b border-line last:border-b-0 hover:bg-elevated',
        interactive && 'cursor-pointer focus-visible:-outline-offset-2',
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
    </motion.tr>
  )
}

interface CompactRowProps<Row> {
  readonly row: Row
  readonly rowIndex: number
  readonly rowCount: number
  readonly rowHeight: number
  readonly render: (row: Row) => ReactNode
  readonly onRowActivate?: (row: Row) => void
}

function CompactRow<Row>({
  row,
  rowIndex,
  rowCount,
  rowHeight,
  render,
  onRowActivate,
}: CompactRowProps<Row>) {
  const reduced = useReducedMotion() ?? false
  const interactive = onRowActivate !== undefined
  return (
    <motion.li
      aria-posinset={rowIndex - HEADER_ROWS}
      aria-setsize={rowCount}
      tabIndex={interactive ? 0 : undefined}
      onClick={onRowActivate ? () => onRowActivate(row) : undefined}
      onKeyDown={activationHandler(row, onRowActivate)}
      whileTap={interactive && !reduced ? { scale: PRESS_SCALE } : undefined}
      transition={springTransition('settle', reduced)}
      style={{ minHeight: rowHeight }}
      className={cn(
        'flex min-w-0 flex-col justify-center gap-1.5 px-1 py-2.5',
        interactive && 'cursor-pointer focus-visible:-outline-offset-2 active:bg-elevated',
      )}
    >
      {render(row)}
    </motion.li>
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
  sort: controlledSort,
  onSortChange,
  onRowActivate,
  maxHeight,
  rowHeight = DEFAULT_ROW_HEIGHT,
  renderCompactRow,
  compactRowHeight = DEFAULT_COMPACT_ROW_HEIGHT,
  className,
}: DataTableProps<Row>) {
  const [internalSort, setInternalSort] = useState<SortState | null>(initialSort ?? null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const wide = useMediaQuery(WIDE_QUERY)
  const compact = renderCompactRow !== undefined && !wide

  const controlled = onSortChange !== undefined
  const sort = controlled ? (controlledSort ?? null) : internalSort
  const handleSort = (columnId: string): void => {
    if (onSortChange) onSortChange(columnId)
    else setInternalSort((current) => nextSortState(current, columnId))
  }

  const sortedRows = useMemo(() => {
    // A controlled table is already in the order its owner chose.
    if (controlled) return rows
    const column = columns.find((candidate) => candidate.id === internalSort?.columnId)
    return sortRows(rows, column?.sortValue, internalSort?.direction)
  }, [columns, rows, internalSort, controlled])

  const effectiveRowHeight = compact ? compactRowHeight : rowHeight
  const virtualized = maxHeight !== undefined
  // eslint-disable-next-line react-hooks/incompatible-library -- no React Compiler here; the virtualizer is read during render on purpose
  const virtualizer = useVirtualizer({
    count: sortedRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => effectiveRowHeight,
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

  const body = compact ? (
    // A list, not a sideways-scrolling table: at 390px there is no room for columns.
    <ul
      aria-label={caption}
      className="flex flex-col divide-y divide-line"
      style={{ paddingTop: padTop, paddingBottom: padBottom }}
    >
      {visibleRows.map(({ row, rowIndex }) => (
        <CompactRow
          key={getRowId(row)}
          row={row}
          rowIndex={rowIndex}
          rowCount={sortedRows.length}
          rowHeight={compactRowHeight}
          render={renderCompactRow}
          onRowActivate={onRowActivate}
        />
      ))}
    </ul>
  ) : (
    <table
      aria-rowcount={sortedRows.length + HEADER_ROWS}
      className="w-full border-separate border-spacing-0"
    >
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr aria-rowindex={1}>
          {columns.map((column) => (
            <HeaderCell key={column.id} column={column} sort={sort} onSort={handleSort} />
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
  )

  return (
    <div
      ref={scrollRef}
      // A scrollable region must be reachable by keyboard.
      tabIndex={virtualized ? 0 : undefined}
      role={virtualized ? 'group' : undefined}
      aria-label={virtualized ? `${caption} (scrollable)` : undefined}
      style={virtualized ? { maxHeight } : undefined}
      className={cn(
        'min-w-0',
        compact ? 'overflow-x-hidden overflow-y-auto' : 'overflow-auto',
        className,
      )}
    >
      {body}
    </div>
  )
}
