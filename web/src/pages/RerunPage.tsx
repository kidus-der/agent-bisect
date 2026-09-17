import { useParams } from '@tanstack/react-router'

import { RerunView } from '@/features/run-detail/RerunView'

export function RerunPage() {
  const { runId, rerunId } = useParams({ from: '/runs/$runId/reruns/$rerunId' })
  return (
    <>
      <title>{`${rerunId} · Bisect`}</title>
      <RerunView runId={runId} rerunId={rerunId} />
    </>
  )
}
