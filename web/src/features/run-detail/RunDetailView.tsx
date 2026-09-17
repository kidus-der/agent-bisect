import { useReducedMotion } from 'motion/react'
import { useCallback, useMemo, useState } from 'react'

import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'

import { availableOrNull, useInterventionDiffQuery, useRerunsQuery, useRunDetailQuery } from './api'
import { DELTA, blameVerdict, effectDomain, forestRows, heatCells } from './blame'
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
  const [playhead, setPlayhead] = useState(1)

  const detail = run.data?.data
  const steps = useMemo(() => detail?.steps ?? [], [detail])
  const nSteps = steps.length
  const effects = useMemo(() => detail?.estimate?.step_effects ?? [], [detail])
  const { rewind, start, reset } = useRewindSequence(nSteps, reduced)

  const rerunRows = useMemo(
    () => availableOrNull(reruns.data?.data ?? null)?.reruns ?? [],
    [reruns.data],
  )
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

  const verdict = blameVerdict(detail.estimate)
  const cells = heatCells(nSteps, effects)
  const rows = forestRows(effects, DELTA, detail.estimate?.blamed_step ?? null)
  const domain = effectDomain(effects, DELTA)
  const summary = interventionSummary(
    intervention.data ? availableOrNull(intervention.data.data) : null,
  )
  const states = tapeStepStates({
    nSteps,
    playhead,
    outcome: detail.outcome,
    rewind,
  })

  return (
    <div className="flex flex-col gap-5">
      <RunDetailHeader run={detail} verdict={verdict} simulated={run.data.meta.simulated} />

      <Panel variant="canvas" className="rounded-chart">
        <StepTimeline
          steps={steps}
          states={states}
          cells={cells}
          blamedStep={detail.estimate?.blamed_step ?? null}
          playhead={playhead}
          onPlayheadChange={setPlayhead}
          rewind={rewind}
          onRewind={handleRewind}
          onResetRewind={reset}
          canRewind={treatedAtPlayhead.length > 0}
          rerunCount={treatedAtPlayhead.length || null}
          intervention={rewind && summary ? summary : null}
        />
      </Panel>

      {detail.estimate === null ? (
        <Panel variant="card">
          <NotBisected runId={runId} />
        </Panel>
      ) : null}

      {detail.estimate !== null && detail.estimate.blamed_step === null ? (
        <NoStepBlamed tested={effects.length} delta={DELTA} />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel variant="card" label="step inspector" title={`Step ${playhead}`}>
          <StepInspector runId={runId} step={steps[playhead - 1]} stepIdx={playhead} />
        </Panel>

        <div className="flex min-w-0 flex-col gap-4">
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
                delta={DELTA}
                selectedStep={playhead}
                onSelectStep={setPlayhead}
              />
            </Panel>
          ) : null}

          {rerunRows.length > 0 ? (
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
        </div>
      </div>

      {detail.judge ? (
        <Panel
          variant="card"
          label="judge vs replay"
          title="What the judge guessed, and what re-running measured"
        >
          <JudgeVsReplay
            judge={detail.judge}
            effects={effects}
            blamedStep={detail.estimate?.blamed_step ?? null}
            selectedStep={playhead}
            onSelectStep={setPlayhead}
          />
        </Panel>
      ) : null}
    </div>
  )
}
