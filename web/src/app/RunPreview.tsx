import { BlameBadge } from '@/components/primitives/BlameBadge'
import { HeatStripe } from '@/components/primitives/HeatStripe'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { LoadingRegion, Skeleton } from '@/components/primitives/Skeleton'
import { type RunDetail, useRunDetailQuery } from '@/features/run-detail/api'
import { blameVerdict, heatCells } from '@/features/run-detail/blame'

import { stripeCellWidth } from './stripeCellWidth'

interface RunPreviewProps {
  readonly runId: string
}

function PreviewFacts({ run }: { readonly run: RunDetail }) {
  const verdict = blameVerdict(run.estimate)
  const cells = heatCells(run.steps.length, run.estimate?.step_effects ?? [])
  const tested = cells.filter((cell) => cell.tested).length
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {run.outcome ? (
          <PassFailPill outcome={run.outcome} size="sm" />
        ) : (
          <span className="label-instrument">recording · no outcome yet</span>
        )}
        <span className="num text-small text-ink-muted">{run.steps.length} steps</span>
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="label-instrument">effect by step_</span>
        <HeatStripe
          steps={cells}
          blamedStep={verdict?.step}
          cellWidth={stripeCellWidth(cells.length)}
          showBlameCaption={false}
        />
        <span className="num text-[12px] text-ink-muted">
          {tested} of {cells.length} steps tested
        </span>
      </div>
      {verdict ? (
        <BlameBadge
          step={verdict.step}
          effect={verdict.effect}
          interval={[verdict.low, verdict.high]}
          size="sm"
          className="self-start"
        />
      ) : (
        <span className="text-small text-ink-muted">
          {run.estimate ? 'No step clears δ.' : 'Not bisected yet.'}
        </span>
      )}
    </div>
  )
}

/** The palette's reason for a detail pane: what the run did, before you open it. */
export function RunPreview({ runId }: RunPreviewProps) {
  const query = useRunDetailQuery(runId)
  if (query.isPending) {
    return (
      <LoadingRegion subject="run preview" className="flex flex-col gap-3">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-5 w-44 rounded-pill" />
      </LoadingRegion>
    )
  }
  if (query.isError) {
    return (
      <p className="text-small text-ink-muted">
        Preview unavailable <span className="num">· {query.error.code}</span>
      </p>
    )
  }
  return <PreviewFacts run={query.data.data} />
}
