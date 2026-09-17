import { AsyncSection } from '@/components/primitives/AsyncSection'
import { EmptyState } from '@/components/primitives/EmptyState'
import { Panel } from '@/components/primitives/Panel'
import { PageHeader } from '@/pages/PageHeader'

import type { BenchmarkSummary } from './api'
import { useBenchmarkQuery } from './api'
import { AccuracyHeatmap } from './AccuracyHeatmap'
import { BenchmarkSkeleton } from './BenchmarkSkeleton'
import { BlameFlowSankey } from './BlameFlowSankey'
import { CostHistogram } from './CostHistogram'
import { DatasetExplorer } from './DatasetExplorer'
import { FlakyAblation } from './FlakyAblation'
import { MethodComparison } from './MethodComparison'
import { PositionSlope } from './PositionSlope'

export const EVAL_COMMAND = 'bisect eval --split test'

function BenchmarkSections({ summary }: { readonly summary: BenchmarkSummary }) {
  if (summary.methods.length === 0) {
    return (
      <Panel variant="canvas">
        <EmptyState
          label="no benchmark results"
          title="No faults have been planted"
          description="Inject known faults into recorded runs, then evaluate how often each method blames the planted step."
          command="bisect inject --out data/faults.parquet"
        />
      </Panel>
    )
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-6">
      <MethodComparison methods={summary.methods} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_2fr]">
        <AccuracyHeatmap cells={summary.heatmap} />
        <PositionSlope rows={summary.by_position} />
      </div>
      <FlakyAblation ablation={summary.flaky_ablation} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BlameFlowSankey rows={summary.sankey} />
        <CostHistogram histogram={summary.cost_histogram} methods={summary.methods} />
      </div>
      <DatasetExplorer />
    </div>
  )
}

export function BenchmarkPage() {
  const query = useBenchmarkQuery()
  return (
    <>
      <PageHeader
        label="benchmark"
        title="Benchmark"
        description="Blame accuracy against planted faults, by method, fault type, step position and cost."
      />
      <AsyncSection
        query={query}
        subject="benchmark results"
        skeleton={<BenchmarkSkeleton />}
        notMeasured={{
          label: 'benchmark',
          title: 'No evaluation has been run',
          command: EVAL_COMMAND,
        }}
      >
        {(summary) => <BenchmarkSections summary={summary} />}
      </AsyncSection>
    </>
  )
}
