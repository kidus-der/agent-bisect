/**
 * What a single re-run page is allowed to say about itself.
 *
 * The two arms are not symmetric: the treated arm replaces exactly one thing at
 * the fork, the control arm replaces nothing and differs from the recording only
 * by its seed. Wording that blurs the two contradicts the product's one claim,
 * so both the copy and the fork cell's colour role are decided here.
 */
import type { TapeStepState } from '@/components/primitives/TapeStep'

import type { RerunRow } from './api'

export type Arm = RerunRow['arm']

export function forkLabel(arm: Arm): string {
  return arm === 'treated'
    ? 'fork · intervention applied here'
    : 'fork · control · nothing replaced'
}

/** Amber means blame, so only the arm that actually intervened gets it. */
export function forkCellState(arm: Arm): TapeStepState {
  return arm === 'treated' ? 'blamed' : 'ran'
}

/**
 * What a step was for THIS re-run. Derived from the fork, not from the step's
 * own `from_tape` flag: that flag describes the recording, so a control forking
 * at k=1 would otherwise show rows reading "from tape" under a caption saying
 * nothing was.
 */
export function stepPhaseLabel(stepIdx: number, forkStep: number, arm: Arm): string {
  if (stepIdx < forkStep) return 'read from tape · 0 calls'
  if (stepIdx === forkStep) return forkLabel(arm)
  return 're-run live'
}

/** How much of the recording this re-run replayed before going live. */
export function tapePrefixClause(forkStep: number): string {
  if (forkStep <= 1) return 'nothing read from tape · live from step 1'
  if (forkStep === 2) return 'step 1 read from tape · 0 calls'
  return `steps 1–${forkStep - 1} read from tape · 0 calls`
}

function changedClause(changed: number): string {
  const plural = changed === 1 ? 'step' : 'steps'
  return `${changed} ${plural} after the fork came out differently from the recording.`
}

export function rerunSummary(arm: Arm, forkStep: number, changed: number): string {
  if (arm === 'control') {
    const lead = `This control arm replaced nothing at step ${forkStep}; it differs from the recording only by its seed.`
    return changed === 0
      ? `${lead} Every step after the fork came out the same anyway.`
      : `${lead} ${changedClause(changed)}`
  }
  return changed === 0
    ? `Only the intervention at step ${forkStep} differs; every later step came out the same as the recording.`
    : changedClause(changed)
}
