import type { ReactNode } from 'react'

import { availableOrNull } from '@/api/client'
import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'
import { StatePanel } from '@/components/primitives/StatePanel'
import { LoadingRegion } from '@/components/primitives/Skeleton'
import { CostAccuracyScatter, toScatterPoints } from '@/features/overview/CostAccuracyScatter'
import { HeadlineBars } from '@/features/overview/HeadlineBars'
import { HeroRewind } from '@/features/overview/HeroRewind'
import { KpiRow } from '@/features/overview/KpiRow'
import { ProvenancePanel } from '@/features/overview/ProvenancePanel'
import { RecallCurve } from '@/features/overview/RecallCurve'
import { RunsStrip } from '@/features/overview/RunsStrip'
import {
  accuracyIntervals,
  isOverviewPayload,
  useBenchmarkMethodsQuery,
  useOverviewQuery,
} from '@/features/overview/api'

import { PageHeader } from './PageHeader'
import { OverviewSkeleton } from './skeletons'

const EVAL_COMMAND = 'bisect eval --split test'

/**
 * Every state except the result itself keeps the plain page title, so the page
 * always has exactly one h1. Once there is a result, the h1 *is* that result.
 */
function TitledState({ children }: { readonly children: ReactNode }) {
  return (
    <>
      <PageHeader
        label="overview"
        title="Overview"
        description="The headline result: how often each method names the decisive step, each with its own interval."
      />
      {children}
    </>
  )
}

export function OverviewPage() {
  const overview = useOverviewQuery()
  // Only for the accuracy intervals the Overview payload does not carry.
  const benchmark = useBenchmarkMethodsQuery()

  if (overview.isPending) {
    return (
      <TitledState>
        <LoadingRegion
          subject="the headline result"
          failureCount={overview.failureCount}
          failureMessage={overview.failureReason?.message}
        >
          <OverviewSkeleton />
        </LoadingRegion>
      </TitledState>
    )
  }

  if (overview.isError) {
    return (
      <TitledState>
        <StatePanel>
          <ErrorState
            title="The headline result did not load"
            message={overview.error.message}
            code={overview.error.code}
            onRetry={() => void overview.refetch()}
          />
        </StatePanel>
      </TitledState>
    )
  }

  const payload = availableOrNull(overview.data.data)

  if (payload !== null && !isOverviewPayload(payload)) {
    return (
      <TitledState>
        <StatePanel>
          <ErrorState
            title="The server answered with an unexpected shape"
            message="/api/overview returned a payload this dashboard does not recognise. Rather than draw a number that might be the wrong one, it draws none — check that the server and this build are the same version."
            code="unexpected_payload"
            onRetry={() => void overview.refetch()}
          />
        </StatePanel>
      </TitledState>
    )
  }

  if (!payload) {
    return (
      <TitledState>
        <Panel variant="canvas">
          <EmptyState
            label="no evaluation yet"
            title="Nothing has been measured"
            description="Overview reports step accuracy against the best judge once an evaluation has run. Until then there is no number to show, so none is shown."
            command={EVAL_COMMAND}
          />
        </Panel>
      </TitledState>
    )
  }

  const methods = availableOrNull(benchmark.data?.data ?? null)?.methods ?? null
  const scatterPoints = toScatterPoints(payload.cost_vs_accuracy, accuracyIntervals(methods))

  return (
    <>
      <title>Overview · Bisect</title>
      <div className="flex flex-col gap-4 lg:gap-6">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:gap-6">
          <HeadlineBars
            headline={payload.headline}
            simulated={overview.data.meta.simulated}
            sampleSize={payload.kpis.failures_diagnosed}
          />
          {/* The rail beside the hero: the four figures, then what produced them. */}
          <div className="flex flex-col gap-3 lg:gap-4">
            <KpiRow kpis={payload.kpis} className="lg:grid-cols-1" />
            <ProvenancePanel />
          </div>
        </div>

        <HeroRewind run={payload.hero_run} />

        <div className="grid gap-4 lg:grid-cols-2 lg:gap-6">
          <RecallCurve points={payload.recall_at_m} provenance={payload.recall_provenance} />
          <CostAccuracyScatter
            points={scatterPoints}
            intervalsUnavailable={!benchmark.isPending && methods === null}
          />
        </div>

        <RunsStrip />
      </div>
    </>
  )
}
