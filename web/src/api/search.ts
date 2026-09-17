/**
 * `/api/search` — runs and static pages for the command palette. The server
 * does the matching, so the palette never has to hold the run list in memory.
 */
import { type UseQueryResult, useQuery } from '@tanstack/react-query'

import { type ApiError, type ApiResult, type Schemas, apiFetch } from './client'

export type SearchHit = Readonly<Schemas['SearchHit']>
export type SearchResults = Readonly<Schemas['SearchResults']>

/** One character matches most of the corpus; two is where the results mean something. */
export const MIN_SEARCH_CHARS = 2
export const SEARCH_DEBOUNCE_MS = 180

export const searchKeys = {
  query: (query: string) => ['search', query] as const,
}

export function useSearchQuery(
  query: string,
): UseQueryResult<ApiResult<SearchResults>, ApiError> {
  const trimmed = query.trim()
  return useQuery<ApiResult<SearchResults>, ApiError>({
    queryKey: searchKeys.query(trimmed),
    queryFn: ({ signal }) =>
      apiFetch<SearchResults>(`/search?q=${encodeURIComponent(trimmed)}`, { signal }),
    enabled: trimmed.length >= MIN_SEARCH_CHARS,
    // A palette that keeps showing yesterday's matches is worse than one that blinks.
    staleTime: 0,
  })
}

export function runHits(results: SearchResults | undefined): readonly SearchHit[] {
  return (results?.hits ?? []).filter((hit) => hit.kind === 'run')
}
