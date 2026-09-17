import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { formatEffect, formatInterval } from '@/lib/format'

import type { EstimatorConfig } from './api'
import type { BlameVerdict } from './blame'

interface BlameReadoutProps {
  readonly verdict: BlameVerdict | null
  readonly delta: number
  readonly testedSteps: number
  readonly bisected: boolean
  /** The settings this run's estimate was actually produced with. */
  readonly config: EstimatorConfig | null
}

function Caption({ children }: { readonly children: React.ReactNode }) {
  return <p className="text-small text-pretty text-ink-muted">{children}</p>
}

/** Short enough for the rail; the full name is the abbreviation's title. */
const BOUNDARY_LABELS: Readonly<Record<EstimatorConfig['efficacy_boundary'], string>> = {
  obf: 'OBF',
  none: 'none',
}
const BOUNDARY_TITLES: Readonly<Record<EstimatorConfig['efficacy_boundary'], string>> = {
  obf: 'O’Brien-Fleming efficacy boundary',
  none: 'no efficacy boundary',
}

/** The estimator's own settings, read off the run rather than assumed. */
function Method({ config }: { readonly config: EstimatorConfig }) {
  const facts: ReadonlyArray<readonly [string, string]> = [
    ['δ', config.delta.toFixed(2)],
    ['conf', `${Math.round(config.conf * 100)}%`],
    ['N ≤', String(config.max_n)],
    ['batch', String(config.batch)],
    ['control', config.control_mode],
  ]
  return (
    <dl
      data-testid="estimator-config"
      className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-line pt-3"
    >
      {facts.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-2">
          <dt className="text-[11px] text-ink-muted">{label}</dt>
          <dd className="num text-[11px] text-ink">{value}</dd>
        </div>
      ))}
      <div className="col-span-2 flex items-baseline justify-between gap-2">
        <dt className="text-[11px] text-ink-muted">boundary</dt>
        <dd className="num text-[11px] text-ink">
          <abbr title={BOUNDARY_TITLES[config.efficacy_boundary]} className="no-underline">
            {BOUNDARY_LABELS[config.efficacy_boundary]}
          </abbr>
        </dd>
      </div>
    </dl>
  )
}

/**
 * The number the whole product exists to produce, at stat size beside the tape.
 * It is never shown without its interval or without the threshold it cleared.
 */
export function BlameReadout({ verdict, delta, testedSteps, bisected, config }: BlameReadoutProps) {
  if (!bisected) {
    return (
      <div className="flex flex-col gap-2">
        <InstrumentLabel>blame</InstrumentLabel>
        <p className="num text-stat text-ink-muted">—</p>
        <Caption>Not bisected yet, so there is no effect to report.</Caption>
      </div>
    )
  }

  if (!verdict) {
    return (
      <div className="flex flex-col gap-2">
        <InstrumentLabel>blame</InstrumentLabel>
        <p className="num text-stat text-ink-muted">none</p>
        <Caption>
          {testedSteps} steps tested; no interval cleared δ&nbsp;{delta.toFixed(2)}.
        </Caption>
        {config ? <Method config={config} /> : null}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <InstrumentLabel>blame · step {verdict.step}</InstrumentLabel>
      <p className="flex items-baseline gap-2">
        <span className="num text-stat font-semibold text-blame">
          <span className="sr-only">effect </span>
          {formatEffect(verdict.effect)}
        </span>
      </p>
      <p className="num text-small text-ink-muted">
        <span className="sr-only">95% confidence interval </span>
        {formatInterval(verdict.low, verdict.high)}
      </p>
      <Caption>
        Earliest step whose {config ? Math.round(config.conf * 100) : 95}% interval clears δ&nbsp;
        {delta.toFixed(2)}, out of {testedSteps} tested.
      </Caption>
      {config ? <Method config={config} /> : null}
    </div>
  )
}
