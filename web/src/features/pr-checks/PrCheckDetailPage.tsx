import { Link } from '@tanstack/react-router'
import { ChevronLeft } from 'lucide-react'

import { AsyncSection } from '@/components/primitives/AsyncSection'
import { Panel } from '@/components/primitives/Panel'
import { Skeleton } from '@/components/primitives/Skeleton'
import { PageHeader } from '@/pages/PageHeader'

import { GATE_COMMAND, type PrCheckDetail, usePrCheckQuery } from './api'
import { CommentPreview } from './CommentPreview'
import { DecisiveStepChange } from './DecisiveStepChange'
import { PassRateCompare } from './PassRateCompare'
import { ScenarioTable } from './ScenarioTable'

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Panel variant="canvas" bodyClassName="flex flex-col gap-4">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-9 w-64 max-w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
      </Panel>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel variant="elevated">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="mt-4 h-11 w-40" />
        </Panel>
        <Panel variant="card">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-4 h-40 w-full" />
        </Panel>
      </div>
    </div>
  )
}

function DetailBody({ check }: { readonly check: PrCheckDetail }) {
  return (
    <div className="flex flex-col gap-4 lg:gap-6">
      <PassRateCompare check={check} />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <DecisiveStepChange check={check} />
        <CommentPreview markdown={check.comment_markdown} prNumber={check.pr_number} />
      </div>
      <ScenarioTable scenarios={check.scenarios} />
    </div>
  )
}

interface PrCheckDetailPageProps {
  readonly checkId: string
}

export function PrCheckDetailPage({ checkId }: PrCheckDetailPageProps) {
  const query = usePrCheckQuery(checkId)
  const title = query.data && 'title' in query.data.data ? query.data.data.title : checkId

  return (
    <>
      <PageHeader
        label={`pr check · ${checkId}`}
        title={title}
        description="What the gate measured on this pull request, and the comment it posts."
        actions={
          <Link
            to="/pr-checks"
            className="inline-flex h-9 items-center gap-1.5 rounded-control border border-line-strong bg-elevated px-3 text-small text-ink hover:border-ink-muted"
          >
            <ChevronLeft aria-hidden="true" className="size-3.5" />
            All checks
          </Link>
        }
      />
      <AsyncSection
        query={query}
        subject="this gate result"
        skeleton={<DetailSkeleton />}
        notMeasured={{
          label: 'pr check',
          title: 'This check has no result yet',
          command: GATE_COMMAND,
        }}
      >
        {(check) => <DetailBody check={check} />}
      </AsyncSection>
    </>
  )
}
