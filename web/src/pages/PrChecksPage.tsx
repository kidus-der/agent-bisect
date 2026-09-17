import { PageStub } from './PageStub'
import { PrChecksSkeleton } from './skeletons'

export function PrChecksPage() {
  return (
    <PageStub
      label="pr checks"
      title="PR checks"
      description="Base vs head on a fixed scenario suite, and the decisive step behind any regression."
      skeleton={<PrChecksSkeleton />}
      empty={{
        label: 'no gate results',
        title: 'No pull request has been gated',
        description:
          'The gate runs the scenario suite on both refs; a drop beyond noise triggers blame on the new failures.',
        command: 'bisect gate --base main --head HEAD',
      }}
    />
  )
}
