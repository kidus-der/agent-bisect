import { PageStub } from './PageStub'
import { BenchmarkSkeleton } from './skeletons'

export function BenchmarkPage() {
  return (
    <PageStub
      label="benchmark"
      title="Benchmark"
      description="Blame accuracy against planted faults: method comparison with intervals, recall@m and cost."
      skeleton={<BenchmarkSkeleton />}
      empty={{
        label: 'no benchmark results',
        title: 'No faults have been planted',
        description:
          'Inject known faults into recorded runs, then evaluate how often each method blames the planted step.',
        command: 'bisect inject --out data/faults.parquet',
      }}
    />
  )
}
