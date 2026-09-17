import { useParams } from '@tanstack/react-router'

import { RunDetailView } from '@/features/run-detail/RunDetailView'

export function RunDetailPage() {
  const { runId } = useParams({ from: '/runs/$runId' })
  return <RunDetailView runId={runId} />
}
