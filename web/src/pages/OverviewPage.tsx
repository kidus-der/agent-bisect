import { PageStub } from './PageStub'
import { OverviewSkeleton } from './skeletons'

export function OverviewPage() {
  return (
    <PageStub
      label="overview"
      title="Overview"
      description="The headline result: pass rate with and without the intervention, each with its interval."
      skeleton={<OverviewSkeleton />}
      empty={{
        label: 'no evaluation yet',
        title: 'Nothing has been measured',
        description:
          'Overview reports treated vs control pass rates once an evaluation has run. Until then there is no number to show, so none is shown.',
        command: 'bisect eval --split test',
      }}
    />
  )
}
