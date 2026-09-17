import { describe, expect, test } from 'vitest'

import type { DatasetEntry } from './api'
import {
  ANY,
  type DatasetFilters,
  EMPTY_FILTERS,
  applyFilters,
  domainsIn,
  hasActiveFilters,
} from './datasetFilters'

function entry(overrides: Partial<DatasetEntry> = {}): DatasetEntry {
  return {
    run_id: 'run-001',
    domain: 'airline',
    task_id: 'refund_after_cancellation',
    fault_type: 'wrong_value',
    planted_step: 7,
    position_bucket: 'middle',
    split: 'test',
    base_pass_rate: 0.88,
    faulted_pass_rate: 0.12,
    ...overrides,
  }
}

const ENTRIES = [
  entry(),
  entry({ run_id: 'run-002', fault_type: 'tool_error', position_bucket: 'early', split: 'dev' }),
  entry({ run_id: 'run-003', domain: 'retail', task_id: 'return_window_dispute' }),
]

describe('applyFilters', () => {
  test('returns everything when nothing is filtered', () => {
    expect(applyFilters(ENTRIES, EMPTY_FILTERS)).toHaveLength(3)
  })

  test('narrows to one fault type', () => {
    // Arrange
    const filters: DatasetFilters = { ...EMPTY_FILTERS, faultType: 'tool_error' }

    // Act / Assert
    expect(applyFilters(ENTRIES, filters).map((row) => row.run_id)).toEqual(['run-002'])
  })

  test('combines filters with AND', () => {
    // Arrange
    const filters: DatasetFilters = { ...EMPTY_FILTERS, split: 'test', domain: 'retail' }

    // Act / Assert
    expect(applyFilters(ENTRIES, filters).map((row) => row.run_id)).toEqual(['run-003'])
  })

  test('matches the query against the run id and the task id, ignoring case', () => {
    expect(applyFilters(ENTRIES, { ...EMPTY_FILTERS, query: 'RUN-003' })).toHaveLength(1)
    expect(applyFilters(ENTRIES, { ...EMPTY_FILTERS, query: 'return_window' })).toHaveLength(1)
  })

  test('returns nothing when no row matches, rather than falling back to everything', () => {
    expect(applyFilters(ENTRIES, { ...EMPTY_FILTERS, query: 'nothing-here' })).toEqual([])
  })

  test('does not mutate the rows it was given', () => {
    // Arrange
    const before = JSON.stringify(ENTRIES)

    // Act
    applyFilters(ENTRIES, { ...EMPTY_FILTERS, split: 'dev' })

    // Assert
    expect(JSON.stringify(ENTRIES)).toBe(before)
  })
})

describe('hasActiveFilters', () => {
  test('is false for the empty filter set', () => {
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false)
  })

  test('ignores a query of only whitespace', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, query: '   ' })).toBe(false)
  })

  test('is true once any facet is set', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, position: 'late' })).toBe(true)
  })
})

describe('domainsIn', () => {
  test('lists each domain once, sorted', () => {
    expect(domainsIn(ENTRIES)).toEqual(['airline', 'retail'])
  })

  test('offers nothing when there are no rows', () => {
    expect(domainsIn([])).toEqual([])
  })

  test('never offers the any sentinel as a domain', () => {
    expect(domainsIn(ENTRIES)).not.toContain(ANY)
  })
})
