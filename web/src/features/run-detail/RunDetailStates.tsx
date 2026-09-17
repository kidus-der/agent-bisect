import { EmptyState } from '@/components/primitives/EmptyState'
import { Panel } from '@/components/primitives/Panel'
import { LoadingRegion, Skeleton } from '@/components/primitives/Skeleton'

const TAPE_CELLS = Array.from({ length: 12 }, (_, index) => index)
const FOREST_ROWS = Array.from({ length: 5 }, (_, index) => index)

/** The page's own layout drawn in blocks, so loading never reflows into something else. */
export function RunDetailSkeleton() {
  return (
    <LoadingRegion subject="this run" className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Panel variant="canvas" label="tape">
        <Skeleton className="h-5 w-24" />
        <div className="mt-3 grid grid-cols-12 gap-1">
          {TAPE_CELLS.map((cell) => (
            <Skeleton key={cell} className="h-12" />
          ))}
        </div>
        <Skeleton className="mt-3 h-3.5 w-full" />
      </Panel>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel variant="card" label="step inspector">
          <Skeleton className="h-9 w-56" />
          <Skeleton className="mt-3 h-24 w-full rounded-chart" />
          <Skeleton className="mt-3 h-24 w-full rounded-chart" />
        </Panel>
        <div className="flex flex-col gap-4">
          <Panel variant="chart" label="forest plot">
            {FOREST_ROWS.map((row) => (
              <Skeleton key={row} className="mt-2 h-5 w-full" />
            ))}
          </Panel>
          <Panel variant="chart" label="treated vs control">
            {FOREST_ROWS.map((row) => (
              <Skeleton key={row} className="mt-2 h-5 w-full" />
            ))}
          </Panel>
        </div>
      </div>
    </LoadingRegion>
  )
}

interface NotBisectedProps {
  readonly runId: string
}

/** A recorded run nobody has bisected yet: say what to run, invent nothing. */
export function NotBisected({ runId }: NotBisectedProps) {
  return (
    <EmptyState
      label="no blame computed"
      title="This run has not been bisected"
      description="Blame rewinds to each candidate step, replaces exactly one thing and re-runs the tail N times against a shared control. Until that runs there is no effect to show, and Bisect will not guess one."
      command={`bisect blame ${runId} --top 3 --n 8`}
    />
  )
}

interface NoStepBlamedProps {
  readonly tested: number
  readonly delta: number
}

/** Tested, but nothing cleared delta. That is a result, not a gap. */
export function NoStepBlamed({ tested, delta }: NoStepBlamedProps) {
  return (
    <Panel variant="card" label="no step blamed">
      <p className="max-w-prose text-pretty text-ink-muted">
        All {tested} tested steps were re-run, and no step&apos;s 95% interval had a lower bound
        above δ&nbsp;{delta.toFixed(2)}. Blame needs the interval to clear the threshold, not just
        the estimate, so this run has no decisive step at this N. Raising N narrows the intervals;
        if it still does not clear, the failure is not attributable to a single step.
      </p>
    </Panel>
  )
}

interface RunNotFoundProps {
  readonly runId: string
}

export function RunNotFound({ runId }: RunNotFoundProps) {
  return (
    <EmptyState
      label="404 · run not found"
      title={`No run ${runId}`}
      description="Nothing with that id is in this recordings index. Check the id, or list what has been recorded."
      command="bisect runs --limit 20"
    />
  )
}
