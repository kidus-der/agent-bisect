import { motion, useReducedMotion } from 'motion/react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { springTransition } from '@/design/motion'
import { formatPercent } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { JobState, JobStatus } from './api'
import { jobFacts } from './jobDetail'

interface StateCopy {
  readonly label: string
  readonly glyph: string
  readonly bar: string
  readonly chip: string
}

/** State is never colour alone: each carries its word and a glyph. */
const JOB_STATE: Readonly<Record<JobState, StateCopy>> = {
  queued: {
    label: 'queued',
    glyph: '·',
    bar: 'bg-tape',
    chip: 'border-line-strong bg-elevated text-ink-muted',
  },
  running: {
    label: 'running',
    glyph: '▸',
    bar: 'bg-measure',
    chip: 'border-measure/40 bg-measure-tint text-measure',
  },
  done: {
    label: 'done',
    glyph: '✓',
    bar: 'bg-pass',
    chip: 'border-pass/40 bg-pass-tint text-pass',
  },
  failed: {
    label: 'failed',
    glyph: '✕',
    bar: 'bg-fail',
    chip: 'border-fail/40 bg-fail-tint text-fail',
  },
}

const JOB_ORDER: readonly JobState[] = ['running', 'queued', 'failed', 'done']

/**
 * What the track should show, given the state.
 *
 * The API's `progress` does not agree with `state` in either direction: a `done`
 * job can carry a stale fraction and render as an empty track, and a `queued`
 * job — which by definition has not started — carries one too. A finished job is
 * drawn full; a queued job is drawn empty and its percentage is withheld rather
 * than asserted, because nothing has been measured yet.
 */
function displayProgress(job: JobStatus): number {
  if (job.state === 'done') return 1
  if (job.state === 'queued') return 0
  return Math.min(1, Math.max(0, job.progress))
}

/** A queued job has no measured progress, so it shows none. */
function progressLabel(job: JobStatus): string {
  return job.state === 'queued' ? '—' : formatPercent(displayProgress(job), 0)
}

function JobTile({ job, index }: { readonly job: JobStatus; readonly index: number }) {
  const reduced = useReducedMotion() ?? false
  const copy = JOB_STATE[job.state]
  const fraction = displayProgress(job)
  return (
    <li className="flex min-w-0 flex-col gap-2.5 rounded-kpi border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="flex min-w-0 flex-col gap-0.5">
          {/* What the job is doing, not just which queue it is in. */}
          <span className="truncate text-h3 font-semibold text-ink">{job.label ?? job.kind}</span>
          <span className="flex flex-wrap items-center gap-x-2">
            <InstrumentLabel>{job.kind}</InstrumentLabel>
            {job.phase ? (
              <span className="rounded-step border border-line-strong bg-elevated px-1 label-instrument text-ink">
                {job.phase}
              </span>
            ) : null}
            <span className="num text-[11px] text-ink-muted">{job.job_id}</span>
          </span>
        </span>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-pill border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap',
            copy.chip,
          )}
        >
          <span aria-hidden="true">{copy.glyph}</span>
          {copy.label}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="block h-2 min-w-0 flex-1 rounded-pill bg-elevated">
          <motion.span
            className={cn('block h-full w-full origin-left rounded-pill', copy.bar)}
            initial={false}
            animate={{ scaleX: fraction }}
            transition={{
              ...springTransition('settle', reduced),
              delay: reduced ? 0 : index * 0.04,
            }}
          />
        </span>
        <span
          className={cn(
            'w-10 shrink-0 text-right num text-small',
            job.state === 'queued' ? 'text-ink-muted' : 'text-ink',
          )}
        >
          {progressLabel(job)}
        </span>
      </div>

      {/* A field the server has not measured shows an em dash, never a zero. */}
      <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-1">
        {jobFacts(job).map((fact) => (
          <div key={fact.label} className="flex items-baseline justify-between gap-2">
            <dt className="label-instrument">{fact.label}</dt>
            <dd
              className={cn(
                'm-0 min-w-0 truncate num text-[12px]',
                fact.value === null ? 'text-ink-muted' : 'text-ink',
              )}
            >
              {fact.value ?? '\u2014'}
            </dd>
          </div>
        ))}
      </dl>

      {job.error ? (
        <p className="text-[12px] text-pretty text-fail">
          <span aria-hidden="true">✕</span> {job.error}
        </p>
      ) : null}
    </li>
  )
}

interface JobQueueProps {
  readonly jobs: readonly JobStatus[]
}

export function JobQueue({ jobs }: JobQueueProps) {
  const ordered = [...jobs].sort((a, b) => JOB_ORDER.indexOf(a.state) - JOB_ORDER.indexOf(b.state))
  const running = jobs.filter((job) => job.state === 'running').length
  return (
    <Panel
      variant="card"
      label="job_queue"
      title="Jobs in flight"
      actions={
        <span className="num text-small text-ink-muted">
          {running} running · {jobs.length} total
        </span>
      }
    >
      {ordered.length === 0 ? (
        <p className="py-6 text-ink-muted">
          Nothing is queued. Start a blame job and it appears here as it runs.
        </p>
      ) : (
        // Tiles rather than full-width rows: three jobs across 1400px turned the
        // progress bar into a 1000px rule that said nothing extra.
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {ordered.map((job, index) => (
            <JobTile key={job.job_id} job={job} index={index} />
          ))}
        </ul>
      )}
    </Panel>
  )
}
