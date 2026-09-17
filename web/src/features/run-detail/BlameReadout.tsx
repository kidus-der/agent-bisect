import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { formatEffect, formatInterval } from '@/lib/format'

import type { BlameVerdict } from './blame'

interface BlameReadoutProps {
  readonly verdict: BlameVerdict | null
  readonly delta: number
  readonly testedSteps: number
  readonly bisected: boolean
}

function Caption({ children }: { readonly children: React.ReactNode }) {
  return <p className="text-small text-pretty text-ink-muted">{children}</p>
}

/**
 * The number the whole product exists to produce, at stat size beside the tape.
 * It is never shown without its interval or without the threshold it cleared.
 */
export function BlameReadout({ verdict, delta, testedSteps, bisected }: BlameReadoutProps) {
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
        Earliest step whose 95% interval clears δ&nbsp;{delta.toFixed(2)}, out of {testedSteps}{' '}
        tested.
      </Caption>
    </div>
  )
}
