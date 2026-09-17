import { useQuery } from '@tanstack/react-query'

import { type Schemas, apiFetch } from '@/api/client'
import { isNotAvailable } from '@/api/payload'

type LiveSnapshot = Readonly<Schemas['LiveSnapshot']>

/** Slow enough to be a nav badge rather than a second live feed. */
const POLL_INTERVAL_MS = 20_000

/**
 * Whether any job is running. Polled, not streamed: the badge has to be right
 * on every page, and a second SSE connection for a 6px dot is not worth it.
 */
export function useRunningJobCount(): number {
  const query = useQuery({
    queryKey: ['live', 'running-jobs'],
    queryFn: ({ signal }) => apiFetch<LiveSnapshot>('/live/snapshot', { signal }),
    refetchInterval: POLL_INTERVAL_MS,
    retry: false,
  })
  const data = query.data?.data
  if (!data || isNotAvailable(data)) return 0
  // A badge must never be the thing that breaks the shell, so the payload is
  // checked rather than trusted: an older server may not send `jobs` at all.
  if (!Array.isArray(data.jobs)) return 0
  return data.jobs.filter((job) => job.state === 'running').length
}
