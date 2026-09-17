import { availableOrNull } from '@/api/client'
import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'
import { LoadingRegion } from '@/components/primitives/Skeleton'
import { CostAccuracyScatter, toScatterPoints } from '@/features/overview/CostAccuracyScatter'
import { HeadlineBars } from '@/features/overview/HeadlineBars'
import { HeroRewind } from '@/features/overview/HeroRewind'
import { KpiRow } from '@/features/overview/KpiRow'
import { RecallCurve } from '@/features/overview/RecallCurve'
import { RunsStrip } from '@/features/overview/RunsStrip'
import {
  accuracyIntervals,
  useBenchmarkMethodsQuery,
  useOverviewQuery,
} from '@/features/overview/api'

import { OverviewSkeleton } from './skeletons'

const EVAL_COMMAND = 'bisect eval --split test'

export function OverviewPage() {
  const overview = useOverviewQuery()
  // Only for the accuracy intervals the Overview payload does not carry.
  const benchmark = useBenchmarkMethodsQuery()

  if (overview.isPending) {
    return (
      <>
        <title>Overview · Bisect</title>
        <LoadingRegion subject="the headline result">
          <OverviewSkeleton />
        </LoadingRegion>
      </>
    )
  }

  if (overview.isError) {
    return (
      <>
        <title>Overview · Bisect</title>
        <Panel variant="card">
          <ErrorState
            title="Cannot reach the Bisect server"
            message={overview.error.message}
            code={overview.error.code}
            onRetry={() => void overview.refetch()}
          />
        </Panel>
      </>
    )
  }

  const data = availableOrNull(overview.data.data)
  if (!data) {
    return (
      <>
        <title>Overview · Bisect</title>
        <Panel variant="canvas">
          <EmptyState
            label="no evaluation yet"
            title="Nothing has been measured"
            description="Overview reports step accuracy against the best judge once an evaluation has run. Until then there is no number to show, so none is shown."
            command={EVAL_COMMAND}
          />
        </Panel>
      </>
    )
  }

  const methods = availableOrNull(benchmark.data?.data ?? null)?.methods ?? null
  const scatterPoints = toScatterPoints(data.cost_vs_accuracy, accuracyIntervals(methods))

  return (
    <>
      <title>Overview · Bisect</title>
      <div className="flex flex-col gap-4 lg:gap-6">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:gap-6">
          <HeadlineBars
            headline={data.headline}
            simulated={overview.data.meta.simulated}
            sampleSize={data.kpis.failures_diagnosed}
          />
          <div className="flex flex-col gap-4">
            <KpiRow kpis={data.kpis} />
          </div>
        </div>

        <HeroRewind run={data.hero_run} />

        <div className="grid gap-4 lg:grid-cols-2 lg:gap-6">
          <RecallCurve points={data.recall_at_m} />
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
