import { useReducedMotion } from 'motion/react'
import { useCallback, useMemo, useState } from 'react'

import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'

import {
  availableOrNull,
  unwrapReruns,
  useInterventionDiffQuery,
  useRerunsQuery,
  useRunDetailQuery,
} from './api'
import { BlameReadout } from './BlameReadout'
import { blameVerdict, deltaFor, effectDomain, forestRows, heatCells } from './blame'
import { DotMatrix } from './DotMatrix'
import { ForestPlot } from './ForestPlot'
import { interventionSummary } from './intervention'
import { JudgeVsReplay } from './JudgeVsReplay'
import { NoStepBlamed, NotBisected, RunDetailSkeleton, RunNotFound } from './RunDetailStates'
import { RunDetailHeader } from './RunDetailHeader'
import { StepInspector } from './StepInspector'
import { StepTimeline } from './StepTimeline'
import { tapeStepStates } from './tapeState'
import { useRewindSequence } from './useRewindSequence'

interface RunDetailViewProps {
  readonly runId: string
}

/** The centrepiece: one run, its tape, its per-step effects and the judge beside them. */
export function RunDetailView({ runId }: RunDetailViewProps) {
  const reduced = useReducedMotion() ?? false
  const run = useRunDetailQuery(runId)
  const reruns = useRerunsQuery(runId)
  const [selected, setSelected] = useState<number | null>(null)

  const detail = run.data?.data
  const steps = useMemo(() => detail?.steps ?? [], [detail])
  const nSteps = steps.length
  const effects = useMemo(() => detail?.estimate?.step_effects ?? [], [detail])
  // The page opens on the step it is about; before that is loaded, on step 1.
  const playhead = selected ?? detail?.estimate?.blamed_step ?? 1
  const setPlayhead = setSelected
  const { rewind, start, reset } = useRewindSequence(nSteps, reduced)

  const rerunsView = useMemo(() => unwrapReruns(reruns), [reruns])
  const rerunRows = rerunsView.rows
  const treatedAtPlayhead = useMemo(
    () => rerunRows.filter((row) => row.arm === 'treated' && row.step === playhead),
    [rerunRows, playhead],
  )
  const intervention = useInterventionDiffQuery(
    runId,
    treatedAtPlayhead.length > 0 ? playhead : null,
  )

  const handleRewind = useCallback(() => {
    const passed = treatedAtPlayhead.some((row) => row.passed)
    start(playhead, treatedAtPlayhead.length === 0 ? null : passed)
  }, [playhead, start, treatedAtPlayhead])

  if (run.isPending) return <RunDetailSkeleton />
  if (run.isError) {
    if (run.error.code === 'not_found') return <RunNotFound runId={runId} />
    return (
      <ErrorState
        title="This run failed to load"
        message={run.error.message}
        code={run.error.code}
        onRetry={() => void run.refetch()}
      />
    )
  }
  if (!detail) return <RunNotFound runId={runId} />

  // `!= null` on purpose: a payload that omits `estimate` must not crash the page.
  const bisected = detail.estimate != null
  const blamedStep = detail.estimate?.blamed_step ?? null
  // The threshold and shortlist size this run was actually decided with.
  const config = detail.estimate?.config ?? null
  const delta = deltaFor(detail.estimate)

  const verdict = blameVerdict(detail.estimate)
  const cells = heatCells(nSteps, effects)
  const rows = forestRows(effects, delta, blamedStep)
  const domain = effectDomain(effects, delta)
  const summary = interventionSummary(
    intervention.data ? availableOrNull(intervention.data.data) : null,
  )
  const states = tapeStepStates({
    nSteps,
    playhead,
    outcome: detail.outcome,
    blamedStep,
    rewind,
  })

  return (
    <div className="flex flex-col gap-5">
      <RunDetailHeader
        runId={runId}
        run={detail}
        verdict={verdict}
        simulated={run.data.meta.simulated}
      />

      <Panel
        variant="canvas"
        className="rounded-chart"
        bodyClassName="flex flex-col gap-6 xl:flex-row xl:items-start xl:gap-8"
      >
        <div className="min-w-0 flex-1">
          <StepTimeline
            steps={steps}
            states={states}
            cells={cells}
            blamedStep={blamedStep}
            playhead={playhead}
            onPlayheadChange={setPlayhead}
            rewind={rewind}
            onRewind={handleRewind}
            onResetRewind={reset}
            canRewind={treatedAtPlayhead.length > 0}
            rerunCount={treatedAtPlayhead.length || null}
            intervention={rewind && summary ? summary : null}
          />
        </div>
        <div className="shrink-0 border-t border-line pt-4 xl:w-56 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-6">
          <BlameReadout
            verdict={verdict}
            delta={delta}
            testedSteps={effects.length}
            bisected={bisected}
            config={config}
          />
        </div>
      </Panel>

      {!bisected ? (
        <Panel variant="card">
          <NotBisected runId={runId} />
        </Panel>
      ) : null}

      {bisected && blamedStep === null ? (
        <NoStepBlamed tested={effects.length} delta={delta} />
      ) : null}

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Panel variant="card" label="step inspector" title={`Step ${playhead}`}>
          <StepInspector runId={runId} step={steps[playhead - 1]} stepIdx={playhead} />
        </Panel>

        {rows.length > 0 ? (
          <Panel
            variant="chart"
            label="forest plot"
            title="Effect per tested step"
            bodyClassName="min-w-0"
          >
            <ForestPlot
              rows={rows}
              domain={domain}
              delta={delta}
              selectedStep={playhead}
              onSelectStep={setPlayhead}
            />
          </Panel>
        ) : null}
      </div>

      {rerunsView.status === 'error' ? (
        <Panel variant="chart" label="treated vs control">
          <ErrorState
            title="The individual re-runs failed to load"
            message={rerunsView.reason ?? 'The request failed.'}
            onRetry={() => void reruns.refetch()}
          />
        </Panel>
      ) : rerunRows.length > 0 ? (
        <Panel
          variant="chart"
          label="treated vs control"
          title={`${rerunRows.length} individual re-runs`}
        >
          <DotMatrix
            rows={rerunRows}
            runId={runId}
            selectedStep={playhead}
            onSelectStep={setPlayhead}
          />
        </Panel>
      ) : null}

      {detail.judge ? (
        <Panel
          variant="card"
          label="judge vs replay"
          title="What the judge guessed, and what re-running measured"
        >
          <JudgeVsReplay
            judge={detail.judge}
            effects={effects}
            blamedStep={blamedStep}
            shortlistM={config?.shortlist_m ?? null}
            selectedStep={playhead}
            onSelectStep={setPlayhead}
          />
        </Panel>
      ) : null}
    </div>
  )
}
