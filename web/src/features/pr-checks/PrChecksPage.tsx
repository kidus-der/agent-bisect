import { Link } from '@tanstack/react-router'
import { ChevronRight } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import { AsyncSection } from '@/components/primitives/AsyncSection'
import { EmptyState } from '@/components/primitives/EmptyState'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { Skeleton } from '@/components/primitives/Skeleton'
import { STAGGER_SECONDS, springTransition } from '@/design/motion'
import { formatPValue, formatPercent, formatPoints } from '@/lib/stats'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/pages/PageHeader'

import { GATE_COMMAND, type PrCheckSummary, usePrChecksQuery } from './api'

const LIST_SKELETON_ROWS = [0, 1, 2, 3]
/** Below this the change is a rounding artefact, not a direction. */
const FLAT_CHANGE = 0.005
const PERCENT = 100

interface RateSparkProps {
  readonly base: number
  readonly head: number
  readonly regressed: boolean
}

/** Two stacked rules on a shared 0-100% scale: base above, head below. */
function RateSpark({ base, head, regressed }: RateSparkProps) {
  return (
    <span aria-hidden="true" className="hidden w-full shrink-0 flex-col gap-1.5 md:flex">
      <span className="block h-1.5 rounded-pill bg-elevated">
        <span
          className="block h-full rounded-pill bg-tape"
          style={{ width: `${Math.min(1, Math.max(0, base)) * PERCENT}%` }}
        />
      </span>
      <span className="block h-1.5 rounded-pill bg-elevated">
        <span
          className={cn('block h-full rounded-pill', regressed ? 'bg-fail' : 'bg-pass')}
          style={{ width: `${Math.min(1, Math.max(0, head)) * PERCENT}%` }}
        />
      </span>
    </span>
  )
}

function CheckCard({ check, index }: { readonly check: PrCheckSummary; readonly index: number }) {
  const reduced = useReducedMotion() ?? false
  const regressed = check.is_regression
  const change = check.head_pass_rate - check.base_pass_rate
  const flat = Math.abs(change) < FLAT_CHANGE
  return (
    <motion.li
      initial={reduced ? undefined : { opacity: 0, y: 8 }}
      animate={reduced ? undefined : { opacity: 1, y: 0 }}
      transition={{
        ...springTransition('settle', reduced),
        delay: reduced ? 0 : index * STAGGER_SECONDS.list,
      }}
    >
      <Link
        to="/pr-checks/$checkId"
        params={{ checkId: check.check_id }}
        className={cn(
          'group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 rounded-card border bg-surface p-4',
          'hover:border-line-strong sm:grid-cols-[minmax(0,1fr)_10rem_8rem_9rem_1.5rem]',
          regressed ? 'border-fail/35' : 'border-line',
        )}
      >
        <span className="flex min-w-0 flex-col gap-1">
          <span className="flex items-center gap-2">
            <span className="num text-[12px] text-ink-muted">#{check.pr_number}</span>
            <span
              data-verdict={regressed ? 'regression' : 'clean'}
              className={cn(
                'inline-flex items-center gap-1 rounded-pill border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap',
                regressed
                  ? 'border-fail/40 bg-fail-tint text-fail'
                  : 'border-pass/40 bg-pass-tint text-pass',
              )}
            >
              <span aria-hidden="true">{regressed ? '✕' : '✓'}</span>
              {regressed ? 'regression' : 'clean'}
            </span>
          </span>
          <span className="truncate num text-h3 font-semibold text-ink">{check.title}</span>
        </span>

        <RateSpark base={check.base_pass_rate} head={check.head_pass_rate} regressed={regressed} />

        <span className="flex items-baseline justify-end gap-2 num text-small">
          <span className="text-ink-muted">{formatPercent(check.base_pass_rate, 0)}</span>
          <span aria-hidden="true" className="text-ink-muted">
            →
          </span>
          <span className={cn('text-h3', regressed ? 'text-fail' : 'text-ink')}>
            {formatPercent(check.head_pass_rate, 0)}
          </span>
        </span>

        <span className="col-span-2 flex items-baseline justify-end gap-4 sm:col-span-1">
          <span
            className={cn(
              'num text-small',
              flat ? 'text-ink-muted' : regressed ? 'text-fail' : 'text-pass',
            )}
          >
            {formatPoints(change, 0)}
          </span>
          <span className="num text-[12px] text-ink-muted">p {formatPValue(check.p_value)}</span>
        </span>

        <ChevronRight
          aria-hidden="true"
          className="hidden size-4 text-ink-muted group-hover:text-ink sm:block"
        />
      </Link>
    </motion.li>
  )
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      {LIST_SKELETON_ROWS.map((row) => (
        <Panel key={row} variant="card">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-5 w-64 max-w-full" />
        </Panel>
      ))}
    </div>
  )
}

function CheckList({ checks }: { readonly checks: readonly PrCheckSummary[] }) {
  if (checks.length === 0) {
    return (
      <Panel variant="canvas">
        <EmptyState
          label="no gate results"
          title="No pull request has been gated"
          description="The gate runs the scenario suite on both refs; a drop beyond noise triggers blame on the new failures."
          command={GATE_COMMAND}
        />
      </Panel>
    )
  }
  const regressions = checks.filter((check) => check.is_regression).length
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <span className="flex items-baseline gap-2">
          <span className="num text-stat text-fail">{regressions}</span>
          <InstrumentLabel>flagged</InstrumentLabel>
        </span>
        <span className="flex items-baseline gap-2">
          <span className="num text-stat text-ink">{checks.length - regressions}</span>
          <InstrumentLabel>clean</InstrumentLabel>
        </span>
      </div>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {checks.map((check, index) => (
          <CheckCard key={check.check_id} check={check} index={index} />
        ))}
      </ul>
    </div>
  )
}

export function PrChecksPage() {
  const query = usePrChecksQuery()
  return (
    <>
      <PageHeader
        label="pr checks"
        title="PR checks"
        description="Base vs head on a fixed scenario suite, and the decisive step behind any regression."
      />
      <AsyncSection
        query={query}
        subject="gate results"
        skeleton={<ListSkeleton />}
        notMeasured={{
          label: 'pr checks',
          title: 'No pull request has been gated',
          command: GATE_COMMAND,
        }}
      >
        {(checks) => <CheckList checks={checks} />}
      </AsyncSection>
    </>
  )
}
