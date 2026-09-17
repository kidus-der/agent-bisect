/**
 * The Runs view as URL search params, so any filtered, sorted view is a link
 * someone can paste. Everything here is parsed defensively: a URL is external
 * input, and an unknown value falls back to the default rather than reaching
 * the API.
 */
import {
  FAULT_TYPES,
  type FaultType,
  type RunOutcome,
  type RunStatus,
  SORTABLE_RUN_FIELDS,
  type ServerRunFilters,
  type SortableRunField,
} from './api'

export type SortDirection = 'asc' | 'desc'

export interface RunsSearch {
  /** Free text over run id and task id, narrowed client-side. */
  readonly q: string
  readonly domain: string | null
  readonly outcome: RunOutcome | null
  readonly status: RunStatus | null
  readonly model: string | null
  readonly fault: FaultType | null
  readonly sort: SortableRunField
  readonly dir: SortDirection
}

export const DEFAULT_RUNS_SEARCH: RunsSearch = {
  q: '',
  domain: null,
  outcome: null,
  status: null,
  model: null,
  fault: null,
  sort: 'run_id',
  dir: 'asc',
}

const OUTCOMES: readonly RunOutcome[] = ['pass', 'fail']
const STATUSES: readonly RunStatus[] = ['recording', 'complete']
const MAX_TEXT_CHARS = 120

function text(value: unknown): string {
  return typeof value === 'string' ? value.slice(0, MAX_TEXT_CHARS) : ''
}

function nullableText(value: unknown): string | null {
  const parsed = text(value).trim()
  return parsed === '' ? null : parsed
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.find((candidate) => candidate === value) ?? null
}

export function validateRunsSearch(input: Record<string, unknown>): RunsSearch {
  return {
    q: text(input.q),
    domain: nullableText(input.domain),
    outcome: oneOf(input.outcome, OUTCOMES),
    status: oneOf(input.status, STATUSES),
    model: nullableText(input.model),
    fault: oneOf(input.fault, FAULT_TYPES),
    sort: oneOf(input.sort, SORTABLE_RUN_FIELDS) ?? DEFAULT_RUNS_SEARCH.sort,
    dir: oneOf<SortDirection>(input.dir, ['asc', 'desc']) ?? DEFAULT_RUNS_SEARCH.dir,
  }
}

/** Default values are dropped, so a shared link carries only what was chosen. */
export function toSearchParams(search: RunsSearch): Record<string, string | undefined> {
  const same = <K extends keyof RunsSearch>(key: K): boolean =>
    search[key] === DEFAULT_RUNS_SEARCH[key]
  const value = <K extends keyof RunsSearch>(key: K): string | undefined =>
    same(key) || search[key] === null ? undefined : String(search[key])
  return {
    q: search.q === '' ? undefined : search.q,
    domain: value('domain'),
    outcome: value('outcome'),
    status: value('status'),
    model: value('model'),
    fault: value('fault'),
    sort: value('sort'),
    dir: value('dir'),
  }
}

export function serverFilters(search: RunsSearch): ServerRunFilters {
  return {
    domain: search.domain,
    outcome: search.outcome,
    status: search.status,
    model: search.model,
    sort: search.sort,
    descending: search.dir === 'desc',
  }
}

/** Clicking the active column flips direction; a new column starts ascending. */
export function nextSort(search: RunsSearch, column: SortableRunField): RunsSearch {
  if (search.sort !== column) return { ...search, sort: column, dir: 'asc' }
  return { ...search, dir: search.dir === 'asc' ? 'desc' : 'asc' }
}

/** True when anything is narrowing the list, so a "clear filters" action is worth offering. */
export function hasActiveFilters(search: RunsSearch): boolean {
  return (
    search.q !== '' ||
    search.domain !== null ||
    search.outcome !== null ||
    search.status !== null ||
    search.model !== null ||
    search.fault !== null
  )
}

export function clearFilters(search: RunsSearch): RunsSearch {
  return { ...DEFAULT_RUNS_SEARCH, sort: search.sort, dir: search.dir }
}
