import { Suspense } from 'react'

import { CHART_DEMOS } from '@/components/chart-demos'
import { Panel } from '@/components/primitives/Panel'
import { LoadingRegion, Skeleton } from '@/components/primitives/Skeleton'

function ChartFallback({ slug }: { readonly slug: string }) {
  return (
    <Panel variant="chart">
      <LoadingRegion subject={slug}>
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-4 h-56 w-full rounded-chart" />
      </LoadingRegion>
    </Panel>
  )
}

/** Every installed Bklit chart, fed by our tokens. Each demo is its own lazy chunk. */
export function ChartsSection() {
  return (
    <ul className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      {CHART_DEMOS.map(({ slug, Component }) => (
        <li key={slug} className="flex min-w-0 flex-col gap-2 [&>section]:flex-1">
          <code className="font-mono text-[12px] text-ink-muted">@bklit/{slug}</code>
          <Suspense fallback={<ChartFallback slug={slug} />}>
            <Component />
          </Suspense>
        </li>
      ))}
    </ul>
  )
}
