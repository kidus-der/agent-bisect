/**
 * Filtering for the dataset explorer. The API paginates but does not filter, so
 * the page is filtered on the client and the counts say so: "12 of 50 on this
 * page" rather than a total that would be wrong.
 */
import type { DatasetEntry, FaultType, PositionBucket } from './api'

export type SplitName = DatasetEntry['split']

export const ANY = 'any'
export type Filter<T extends string> = T | typeof ANY

export interface DatasetFilters {
  readonly faultType: Filter<FaultType>
  readonly position: Filter<PositionBucket>
  readonly split: Filter<SplitName>
  readonly domain: Filter<string>
  readonly query: string
}

export const EMPTY_FILTERS: DatasetFilters = {
  faultType: ANY,
  position: ANY,
  split: ANY,
  domain: ANY,
  query: '',
}

export function hasActiveFilters(filters: DatasetFilters): boolean {
  return (
    filters.faultType !== ANY ||
    filters.position !== ANY ||
    filters.split !== ANY ||
    filters.domain !== ANY ||
    filters.query.trim() !== ''
  )
}

function matchesQuery(entry: DatasetEntry, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (needle === '') return true
  return entry.run_id.toLowerCase().includes(needle) || entry.task_id.toLowerCase().includes(needle)
}

export function applyFilters(
  entries: readonly DatasetEntry[],
  filters: DatasetFilters,
): readonly DatasetEntry[] {
  return entries.filter(
    (entry) =>
      (filters.faultType === ANY || entry.fault_type === filters.faultType) &&
      (filters.position === ANY || entry.position_bucket === filters.position) &&
      (filters.split === ANY || entry.split === filters.split) &&
      (filters.domain === ANY || entry.domain === filters.domain) &&
      matchesQuery(entry, filters.query),
  )
}

/** Domains present on this page, so the filter never offers a value with no rows. */
export function domainsIn(entries: readonly DatasetEntry[]): readonly string[] {
  return [...new Set(entries.map((entry) => entry.domain))].sort()
}
