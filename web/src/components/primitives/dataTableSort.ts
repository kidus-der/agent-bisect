export type SortDirection = 'asc' | 'desc'

export interface SortState {
  readonly columnId: string
  readonly direction: SortDirection
}

export type SortValue = number | string | null

/** asc -> desc -> unsorted. Clicking a different column starts at asc. */
export function nextSortState(current: SortState | null, columnId: string): SortState | null {
  if (!current || current.columnId !== columnId) return { columnId, direction: 'asc' }
  return current.direction === 'asc' ? { columnId, direction: 'desc' } : null
}

function compareValues(a: SortValue, b: SortValue): number {
  // Nulls ("not measured") always sort last, regardless of direction.
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'en', { numeric: true })
}

/** Returns a new array; never mutates `rows`. Stable for equal keys. */
export function sortRows<Row>(
  rows: readonly Row[],
  sortValue: ((row: Row) => SortValue) | undefined,
  direction: SortDirection | undefined,
): readonly Row[] {
  if (!sortValue || !direction) return rows
  const sign = direction === 'asc' ? 1 : -1
  return rows
    .map((row, index) => ({ row, index, key: sortValue(row) }))
    .sort((a, b) => {
      if (a.key === null || b.key === null) return compareValues(a.key, b.key) || a.index - b.index
      return compareValues(a.key, b.key) * sign || a.index - b.index
    })
    .map((entry) => entry.row)
}
