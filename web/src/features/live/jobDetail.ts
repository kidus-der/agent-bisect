/**
 * What a job is actually doing, from the fields the server now sends.
 *
 * A blame job is rewinding a run to specific steps and re-running it N times;
 * a progress bar says none of that. Every field here is optional in the schema,
 * so anything the server has not measured is reported as absent rather than
 * guessed at, and the component renders those as an em dash.
 */
import { formatNumber } from '@/lib/format'

import type { JobStatus } from './api'

const SECONDS_PER_MINUTE = 60
const SECONDS_PER_HOUR = 3600

/** `7m 06s`, `1h 12m`, `43s`. */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  if (seconds < SECONDS_PER_MINUTE) return `${Math.round(seconds)}s`
  if (seconds < SECONDS_PER_HOUR) {
    const minutes = Math.floor(seconds / SECONDS_PER_MINUTE)
    const rest = Math.round(seconds - minutes * SECONDS_PER_MINUTE)
    return `${minutes}m ${String(rest).padStart(2, '0')}s`
  }
  const hours = Math.floor(seconds / SECONDS_PER_HOUR)
  const minutes = Math.round((seconds - hours * SECONDS_PER_HOUR) / SECONDS_PER_MINUTE)
  return `${hours}h ${String(minutes).padStart(2, '0')}m`
}

/** `6 / 16`, or absent when the server has not counted them. */
export function formatItems(job: JobStatus): string | null {
  const done = job.items_done
  const total = job.items_total
  if (typeof done !== 'number' || typeof total !== 'number') return null
  return `${formatNumber(done, { decimals: 0 })} / ${formatNumber(total, { decimals: 0 })}`
}

export function formatEta(job: JobStatus): string | null {
  return typeof job.eta_seconds === 'number' ? formatDuration(job.eta_seconds) : null
}

export function formatCalls(job: JobStatus): string | null {
  return typeof job.calls_spent === 'number' ? formatNumber(job.calls_spent, { decimals: 0 }) : null
}

/** The provider model id, trimmed to its name. */
export function shortModel(job: JobStatus): string | null {
  return job.model ? (job.model.split('/').at(-1) ?? job.model) : null
}

export interface JobFact {
  readonly label: string
  /** Null renders as an em dash: the server has not measured it. */
  readonly value: string | null
}

/** The facts a job carries, in reading order. */
export function jobFacts(job: JobStatus): readonly JobFact[] {
  return [
    { label: 'done', value: formatItems(job) },
    { label: 'calls', value: formatCalls(job) },
    { label: 'model', value: shortModel(job) },
    { label: 'eta', value: job.state === 'running' ? formatEta(job) : null },
  ]
}
