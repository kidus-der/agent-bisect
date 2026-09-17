/**
 * Flattens the paged run list and applies the two filters `/api/runs` has no
 * query parameter for. The result carries enough counting for the UI to say
 * exactly what it is showing — "42 of 266" is only honest while every page is
 * loaded, so `allLoaded` is reported too.
 */
import { availableOrNull } from '@/api/client'
import type { ApiResult, NotAvailable } from '@/api/client'

import type { RunListPage, RunSummary } from './api'
import type { RunsSearch } from './runsSearch'

export type RunsPageResult = ApiResult<RunListPage | NotAvailable>

export interface NarrowedRuns {
  readonly rows: readonly RunSummary[]
  /** How many runs the server says match the server-side filters. */
  readonly total: number | null
  /** How many have been fetched so far. */
  readonly loaded: number
  /** True when the server answered `not_available` rather than a list. */
  readonly notAvailable: boolean
}

function matchesText(run: RunSummary, query: string): boolean {
  if (query === '') return true
  const needle = query.toLowerCase()
  return run.run_id.toLowerCase().includes(needle) || run.task_id.toLowerCase().includes(needle)
}

function matchesFault(run: RunSummary, search: RunsSearch): boolean {
  return search.fault === null || run.fault_type === search.fault
}

export function narrowRuns(pages: readonly RunsPageResult[], search: RunsSearch): NarrowedRuns {
  const payloads = pages.map((page) => availableOrNull(page.data))
  const notAvailable = pages.length > 0 && payloads.every((payload) => payload === null)
  const all = payloads.flatMap((payload) => payload?.runs ?? [])
  return {
    rows: all.filter((run) => matchesText(run, search.q) && matchesFault(run, search)),
    total: pages.at(-1)?.meta.total ?? null,
    loaded: all.length,
    notAvailable,
  }
}

/** The values the filter controls offer, taken from the runs actually loaded. */
export interface RunFacets {
  readonly domains: readonly string[]
  readonly models: readonly string[]
}

export function runFacets(pages: readonly RunsPageResult[]): RunFacets {
  const runs = pages.flatMap((page) => availableOrNull(page.data)?.runs ?? [])
  return {
    domains: [...new Set(runs.map((run) => run.domain))].sort(),
    models: [...new Set(runs.map((run) => run.model))].sort(),
  }
}

/**
 * What the count line says. Free text and fault type are applied here rather
 * than by the server, so the wording admits it while pages are still arriving.
 */
export function resultSummary(
  narrowed: NarrowedRuns,
  search: RunsSearch,
  allLoaded: boolean,
): string {
  const { rows, total, loaded } = narrowed
  const narrowedLocally = search.q !== '' || search.fault !== null
  const count = rows.length
  const noun = count === 1 ? 'run' : 'runs'
  if (!narrowedLocally) {
    return total === null ? `${count} ${noun}` : `${count} of ${total} ${noun}`
  }
  if (allLoaded) return `${count} of ${total ?? loaded} ${noun}`
  return `${count} ${noun} in the ${loaded} loaded so far`
}
