/**
 * Turns what the API says about the Overview's hero run into the spec the
 * rewind player consumes. Every field is either measured or null — the player
 * is told what is missing rather than being handed a plausible number.
 */
import type {
  RewindIntervention,
  RewindSpec,
  RewindVerdict,
} from '@/components/rewind/rewindFrames'
import type { InterventionDiff, RunEstimate } from '@/features/run-detail/api'

import type { RunSummary } from './api'

/** Below this a rewind has nothing to replay, so the loop is not shown at all. */
const MIN_STEPS = 3
const MAX_VALUE_CHARS = 24
const FALLBACK_RERUNS = 1

function renderValue(value: unknown): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  if (text === undefined) return 'null'
  return text.length > MAX_VALUE_CHARS ? `${text.slice(0, MAX_VALUE_CHARS - 1)}…` : text
}

/** The first field the intervention actually changed, so the loop can name it. */
export function interventionSummary(diff: InterventionDiff | null): RewindIntervention | null {
  if (!diff) return null
  const before = diff.original_tool_result as Record<string, unknown>
  const after = diff.replaced_tool_result as Record<string, unknown>
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])]
  for (const key of keys) {
    if (renderValue(before[key]) === renderValue(after[key])) continue
    return { field: key, before: renderValue(before[key]), after: renderValue(after[key]) }
  }
  return null
}

/** The measured effect at the blamed step. Null when the step was never tested. */
export function verdictForStep(estimate: RunEstimate | null, step: number): RewindVerdict | null {
  const effect = estimate?.step_effects.find((entry) => entry.step === step)
  if (!effect) return null
  return { step, effect: effect.effect, low: effect.ci_low, high: effect.ci_high }
}

/** How many times the treated arm was re-run at that step. */
export function rerunsForStep(estimate: RunEstimate | null, step: number): number {
  const effect = estimate?.step_effects.find((entry) => entry.step === step)
  return effect?.treated.n ?? estimate?.treated_reruns ?? FALLBACK_RERUNS
}

export interface HeroRunInputs {
  readonly run: RunSummary
  readonly estimate: RunEstimate | null
  readonly interventionDiff: InterventionDiff | null
}

/**
 * Null when this run cannot be replayed as a story: no decisive step, too few
 * steps, or a blamed step with nothing after it to re-run.
 */
export function heroRewindSpec({
  run,
  estimate,
  interventionDiff,
}: HeroRunInputs): RewindSpec | null {
  const target = run.decisive_step
  if (target === null || run.n_steps < MIN_STEPS) return null
  if (target < 2 || target >= run.n_steps) return null
  return {
    stepCount: run.n_steps,
    targetStep: target,
    reruns: rerunsForStep(estimate, target),
    intervention: interventionSummary(interventionDiff),
    verdict: verdictForStep(estimate, target),
  }
}
