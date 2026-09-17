import { AsyncSection } from '@/components/primitives/AsyncSection'
import { EmptyState } from '@/components/primitives/EmptyState'
import { Panel } from '@/components/primitives/Panel'
import { PageHeader } from '@/pages/PageHeader'

import type { BenchmarkSummary } from './api'
import { useBenchmarkQuery } from './api'
import { BenchmarkSkeleton } from './BenchmarkSkeleton'
import { MethodComparison } from './MethodComparison'

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
        description="Blame accuracy against planted faults: method comparison with intervals, by fault type and step position, and what each diagnosis cost."
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
