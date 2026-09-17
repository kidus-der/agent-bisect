/**
 * Drives the rewind: tape band, intervention, then the recorded tail re-stated
 * one step at a time. Reduced motion jumps straight to the settled state, which
 * is the same before/after the animation would have reached.
 */
import { useCallback, useEffect, useState } from 'react'

import { type RewindState, nextRewind } from './tapeState'

/**
 * Cadence of the tail. This is a re-statement of a re-run that already happened,
 * not a live replay, so it is a presentation rhythm, not a measured latency --
 * no progress number is shown against it. `rewinding` is per band slice, not
 * per phase, so the whole band still lands in roughly the same time.
 */
const PHASE_MS: Readonly<Record<RewindState['phase'], number>> = {
  rewinding: 110,
  intervened: 800,
  replaying: 260,
  settled: 0,
}

export interface RewindControls {
  readonly rewind: RewindState | null
  readonly start: (step: number, passed: boolean | null) => void
  readonly reset: () => void
}

export function useRewindSequence(nSteps: number, reduced: boolean): RewindControls {
  const [rewind, setRewind] = useState<RewindState | null>(null)

  const start = useCallback(
    (step: number, passed: boolean | null): void => {
      setRewind(
        reduced
          ? { step, phase: 'settled', replayedThrough: nSteps, passed, bandedThrough: step - 1 }
          : { step, phase: 'rewinding', replayedThrough: step, passed, bandedThrough: 0 },
      )
    },
    [nSteps, reduced],
  )

  const reset = useCallback((): void => setRewind(null), [])

  useEffect(() => {
    if (!rewind || rewind.phase === 'settled') return undefined
    const timer = window.setTimeout(
      () => setRewind((current) => (current ? nextRewind(current, nSteps) : current)),
      PHASE_MS[rewind.phase],
    )
    return () => window.clearTimeout(timer)
  }, [rewind, nSteps])

  return { rewind, start, reset }
}
