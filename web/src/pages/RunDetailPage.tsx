import { useParams } from '@tanstack/react-router'

import { PageStub } from './PageStub'
import { RunDetailSkeleton } from './skeletons'

export function RunDetailPage() {
  const { runId } = useParams({ strict: false })
  const id = runId ?? 'RUN_ID'
  return (
    <PageStub
      label={`run · ${id}`}
      title={id}
      description="The step timeline, the per-step effect estimates and the intervention diff for one run."
      skeleton={<RunDetailSkeleton />}
      empty={{
        label: 'no blame computed',
        title: 'This run has not been bisected',
        description:
          'Blame rewinds to each candidate step, replaces one thing and re-runs the tail N times against a control.',
        command: `bisect blame ${id} --top 3 --n 8`,
      }}
    />
  )
}
