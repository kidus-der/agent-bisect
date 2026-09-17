import { PageStub } from './PageStub'
import { LiveSkeleton } from './skeletons'

export function LivePage() {
  return (
    <PageStub
      label="live"
      title="Live"
      description="Jobs in flight, the call budget and rate-limit headroom, as the server reports them."
      skeleton={<LiveSkeleton />}
      empty={{
        label: 'no jobs in flight',
        title: 'Nothing is running',
        description:
          'Live shows replay jobs while they execute. Start a blame job and its calls appear here as they happen.',
        command: 'bisect blame RUN_ID --top 3 --n 8',
      }}
    />
  )
}
