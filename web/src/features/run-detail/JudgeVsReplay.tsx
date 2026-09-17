import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { SegmentedControl } from '@/components/primitives/SegmentedControl'
import { formatEffect, formatInterval, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

import type { JudgePanel, JudgeProtocol, JudgeRankEntry, StepEffect } from './api'
import { effectForStep, judgeMissed } from './blame'

const ROW_HEIGHT = 46
const CONNECTOR_WIDTH = 56

const PROTOCOLS: ReadonlyArray<{ readonly value: JudgeProtocol; readonly label: string }> = [
  { value: 'all_at_once', label: 'All at once' },
  { value: 'step_by_step', label: 'Step by step' },
]

interface MeasuredEntry {
  readonly step: number
  readonly effect: StepEffect | undefined
  readonly blamed: boolean
}

function measuredOrder(
  ranking: readonly JudgeRankEntry[],
  effects: readonly StepEffect[],
  blamedStep: number | null,
): readonly MeasuredEntry[] {
  const steps = new Set(ranking.map((entry) => entry.step))
  if (blamedStep !== null) steps.add(blamedStep)
  return [...steps]
    .map((step) => ({ step, effect: effectForStep(effects, step), blamed: step === blamedStep }))
    .sort((a, b) => (b.effect?.effect ?? -Infinity) - (a.effect?.effect ?? -Infinity))
}

interface ConnectorsProps {
  readonly ranking: readonly JudgeRankEntry[]
  readonly measured: readonly MeasuredEntry[]
  readonly blamedStep: number | null
}

/** Slope lines: flat means the judge and replay agree on that step's position. */
function Connectors({ ranking, measured, blamedStep }: ConnectorsProps) {
  const height = Math.max(ranking.length, measured.length) * ROW_HEIGHT
  return (
    <svg
      aria-hidden="true"
      width={CONNECTOR_WIDTH}
      height={height}
      viewBox={`0 0 ${CONNECTOR_WIDTH} ${height}`}
      className="shrink-0"
    >
      {ranking.map((entry, index) => {
        const target = measured.findIndex((item) => item.step === entry.step)
        if (target === -1) return null
        const blamed = entry.step === blamedStep
        return (
          <line
            key={entry.step}
            x1={0}
            x2={CONNECTOR_WIDTH}
            y1={(index + 0.5) * ROW_HEIGHT}
            y2={(target + 0.5) * ROW_HEIGHT}
            stroke={blamed ? 'var(--bx-blame)' : 'var(--bx-line-strong)'}
            strokeWidth={blamed ? 2 : 1}
          />
        )
      })}
    </svg>
  )
}

interface JudgeVsReplayProps {
  readonly judge: JudgePanel
  readonly effects: readonly StepEffect[]
  readonly blamedStep: number | null
  readonly selectedStep: number
  readonly onSelectStep: (step: number) => void
}

/** The judge's guess beside the measured effect, with the disagreement drawn. */
export function JudgeVsReplay({
  judge,
  effects,
  blamedStep,
  selectedStep,
  onSelectStep,
}: JudgeVsReplayProps) {
  const [protocol, setProtocol] = useState<JudgeProtocol>('all_at_once')
  const [rationale, setRationale] = useState<string | null>(null)
  const ranking = judge[protocol]
  const measured = measuredOrder(ranking, effects, blamedStep)
  const missed = judgeMissed(ranking, blamedStep)
  const topStep = ranking[0]?.step ?? null
  const agrees = blamedStep !== null && topStep === blamedStep

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          label="Judge protocol"
          options={PROTOCOLS}
          value={protocol}
          onChange={setProtocol}
        />
        <p className="num text-small">
          {blamedStep === null ? (
            <span className="text-ink-muted">no step blamed · nothing to agree on</span>
          ) : agrees ? (
            <span className="text-ink">
              judge rank 1 = step {topStep} ·{' '}
              <span className="text-ink-muted">agrees with replay</span>
            </span>
          ) : (
            <span className="text-ink">
              judge rank 1 = step {topStep ?? 'none'} · replay blames step {blamedStep}
            </span>
          )}
        </p>
      </div>

      {missed ? (
        <p
          role="status"
          className="mb-4 flex items-start gap-2 rounded-chart border border-fail/40 bg-fail-tint px-3 py-2 text-small text-ink"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-fail" />
          <span>
            The judge never shortlisted step {blamedStep}. Replay can only test what the judge
            proposes, so this run is a recall failure, not an accuracy one.
          </span>
        </p>
      ) : null}

      <div className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-start sm:gap-0">
        <ul className="min-w-0 flex-1">
          <li className="mb-1">
            <InstrumentLabel>judge ranking</InstrumentLabel>
          </li>
          {ranking.map((entry) => (
            <li key={entry.step} style={{ height: ROW_HEIGHT }}>
              <button
                type="button"
                onClick={() => onSelectStep(entry.step)}
                onFocus={() => setRationale(entry.rationale)}
                onBlur={() => setRationale(null)}
                onPointerEnter={() => setRationale(entry.rationale)}
                onPointerLeave={() => setRationale(null)}
                aria-pressed={entry.step === selectedStep}
                className={cn(
                  'flex h-10 w-full cursor-pointer items-center justify-between gap-2 rounded-step border px-2 text-left',
                  entry.step === selectedStep
                    ? 'border-judge bg-judge-tint'
                    : 'border-line hover:border-line-strong',
                )}
              >
                <span className="num text-small text-ink">
                  <span className="text-judge">#{entry.rank}</span> step {entry.step}
                </span>
                <span className="num text-small text-ink-muted">
                  <span className="sr-only">judge score </span>
                  {formatNumber(entry.score, { decimals: 3 })}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="hidden pt-6 sm:block">
          <Connectors ranking={ranking} measured={measured} blamedStep={blamedStep} />
        </div>

        <ul className="min-w-0 flex-1">
          <li className="mb-1">
            <InstrumentLabel>measured effect</InstrumentLabel>
          </li>
          {measured.map((item) => (
            <li key={item.step} style={{ height: ROW_HEIGHT }}>
              <button
                type="button"
                onClick={() => onSelectStep(item.step)}
                aria-pressed={item.step === selectedStep}
                className={cn(
                  'flex h-10 w-full cursor-pointer flex-col items-start justify-center gap-0.5 rounded-step border px-2 text-left',
                  item.blamed
                    ? 'border-blame bg-blame-tint'
                    : item.step === selectedStep
                      ? 'border-measure bg-measure-tint'
                      : 'border-line hover:border-line-strong',
                )}
              >
                <span className="num text-small text-ink">
                  step {item.step}
                  {item.effect ? (
                    <span className={cn('ml-2', item.blamed ? 'text-blame' : 'text-measure')}>
                      {formatEffect(item.effect.effect)}
                    </span>
                  ) : (
                    <span className="ml-2 text-ink-muted">not tested</span>
                  )}
                </span>
                {item.effect ? (
                  <span className="num text-[11px] text-ink-muted">
                    <span className="sr-only">95% confidence interval </span>
                    {formatInterval(item.effect.ci_low, item.effect.ci_high)}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <p className="mt-2 min-h-8 border-t border-line pt-2 text-small text-ink-muted">
        {rationale ?? 'Focus a judge row to read its rationale.'}
      </p>
    </div>
  )
}
