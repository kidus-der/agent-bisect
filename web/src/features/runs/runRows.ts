/**
 * Flattens the paged run list. Every filter is the server's, so there is no
 * narrowing to do here — only the counting the result line needs.
 */
import { availableOrNull } from '@/api/client'
import type { ApiResult, NotAvailable } from '@/api/client'

import type { RunListPage, RunSummary } from './api'
import type { RunsSearch } from './runsSearch'
import { hasActiveFilters } from './runsSearch'

export type RunsPageResult = ApiResult<RunListPage | NotAvailable>

export interface NarrowedRuns {
  readonly rows: readonly RunSummary[]
  /** How many runs match the filters, across every page. */
  readonly total: number | null
  /** How many have been fetched so far. */
  readonly loaded: number
  /** True when the server answered `not_available` rather than a list. */
  readonly notAvailable: boolean
}

export function narrowRuns(pages: readonly RunsPageResult[]): NarrowedRuns {
  const payloads = pages.map((page) => availableOrNull(page.data))
  const notAvailable = pages.length > 0 && payloads.every((payload) => payload === null)
  const rows = payloads.flatMap((payload) => payload?.runs ?? [])
  return { rows, total: pages.at(-1)?.meta.total ?? null, loaded: rows.length, notAvailable }
}

/** The values the filter controls offer, taken from the runs actually loaded. */
export interface RunFacets {
  readonly domains: readonly string[]
  readonly models: readonly string[]
}

export const EMPTY_FACETS: RunFacets = { domains: [], models: [] }

export function runFacets(pages: readonly RunsPageResult[]): RunFacets {
  const runs = pages.flatMap((page) => availableOrNull(page.data)?.runs ?? [])
  return {
    domains: [...new Set(runs.map((run) => run.domain))].sort(),
    models: [...new Set(runs.map((run) => run.model))].sort(),
  }
}

/**
 * Facets are derived from the runs on screen, so a filter that matches nothing
 * would empty the filter bar that produced it. Keeping the last non-empty set
 * stops the chrome vanishing at exactly the moment it is needed to recover.
 */
export function stableFacets(current: RunFacets, previous: RunFacets): RunFacets {
  return current.domains.length === 0 && current.models.length === 0 ? previous : current
}

/**
 * What the count line says. `total` already accounts for every filter, so the
 * number is the whole matching set, not just the pages loaded so far.
 */
export function resultSummary(narrowed: NarrowedRuns, search: RunsSearch): string {
  const count = narrowed.total ?? narrowed.loaded
  const one = count === 1
  if (!hasActiveFilters(search)) return `${count} ${one ? 'run' : 'runs'}`
  return one ? '1 run matches' : `${count} runs match`
}
