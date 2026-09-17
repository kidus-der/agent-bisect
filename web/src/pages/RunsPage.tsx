import { PageStub } from './PageStub'
import { TableSkeletonPage } from './skeletons'

export function RunsPage() {
  return (
    <PageStub
      label="runs"
      title="Runs"
      description="Every recorded run. Open one to scrub its tape and see which step carries the blame."
      skeleton={<TableSkeletonPage />}
      empty={{
        label: 'no runs recorded',
        title: 'The tape is empty',
        description:
          'Record a batch of τ² airline tasks. Each run is written to tape so it can be replayed with zero network calls.',
        command: 'bisect record --domain airline --tasks 0-19',
      }}
    />
  )
}
