import { motion, useReducedMotion } from 'motion/react'

import { Panel } from '@/components/primitives/Panel'
import { springTransition } from '@/design/motion'
import { formatPercent } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { JobState, JobStatus } from './api'

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

function JobRow({ job, index }: { readonly job: JobStatus; readonly index: number }) {
  const reduced = useReducedMotion() ?? false
  const copy = JOB_STATE[job.state]
  const fraction = Math.min(1, Math.max(0, job.progress))
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 border-b border-line py-3 last:border-b-0 sm:grid-cols-[8rem_minmax(0,1fr)_5rem_4rem]">
      <span className="num text-small text-ink">{job.job_id}</span>
      <span className="order-3 col-span-2 sm:order-none sm:col-span-1">
        <span aria-hidden="true" className="block h-2 w-full rounded-pill bg-elevated">
          <motion.span
            className={cn('block h-full origin-left rounded-pill', copy.bar)}
            initial={false}
            animate={{ scaleX: fraction }}
            transition={{
              ...springTransition('settle', reduced),
              delay: reduced ? 0 : index * 0.04,
            }}
            style={{ width: '100%' }}
          />
        </span>
      </span>
      <span className="text-right num text-small text-ink-muted sm:text-left">{job.kind}</span>
      <span className="flex items-center justify-end gap-2">
        <span className="num text-small text-ink">{formatPercent(fraction, 0)}</span>
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-pill border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap',
            copy.chip,
          )}
        >
          <span aria-hidden="true">{copy.glyph}</span>
          {copy.label}
        </span>
      </span>
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
        <ul className="m-0 flex list-none flex-col p-0">
          {ordered.map((job, index) => (
            <JobRow key={job.job_id} job={job} index={index} />
          ))}
        </ul>
      )}
    </Panel>
  )
}
