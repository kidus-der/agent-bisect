import { useParams } from '@tanstack/react-router'

import { PrCheckDetailPage as PrCheckDetailView } from '@/features/pr-checks/PrCheckDetailPage'

/** Route component: the id comes from the path, the view stays testable without a router. */
export function PrCheckDetailPage() {
  const { checkId } = useParams({ from: '/pr-checks/$checkId' })
  return <PrCheckDetailView checkId={checkId} />
}
