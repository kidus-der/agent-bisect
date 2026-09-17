/**
 * The blame rule, on the client side of the same contract the estimator uses:
 * blame is the EARLIEST step whose 95% CI lower bound clears delta, never the
 * largest effect (docs/brief/summary.md §9.1).
 */
import type { JudgeRankEntry, StepEffect } from './api'

/**
 * Decision threshold. Mirrors `DEFAULT_DELTA` in
 * `agent_bisect/attribution/estimate.py`; the API does not carry it per run, so
 * the page labels the line it draws with this value rather than leaving it bare.
 */
export const DELTA = 0.1

export function clearsDelta(effect: StepEffect, delta: number): boolean {
  return effect.ci_low > delta
}

/** The earliest clearing step, or null when nothing clears. */
export function earliestClearingStep(effects: readonly StepEffect[], delta: number): number | null {
  const clearing = effects.filter((entry) => clearsDelta(entry, delta))
  if (clearing.length === 0) return null
  return clearing.reduce((earliest, entry) => (entry.step < earliest.step ? entry : earliest)).step
}

export interface BlameVerdict {
  readonly step: number
  readonly effect: number
  readonly low: number
  readonly high: number
}

interface EstimateLike {
  readonly blamed_step: number | null
  readonly step_effects: readonly StepEffect[]
}

/**
 * The blamed step with the numbers that justify it. Blame is never rendered
 * without its effect and interval, so a blamed step with no effect row is no
 * verdict at all.
 */
export function blameVerdict(estimate: EstimateLike | null | undefined): BlameVerdict | null {
  if (!estimate || estimate.blamed_step === null) return null
  const row = estimate.step_effects.find((entry) => entry.step === estimate.blamed_step)
  if (!row) return null
  return { step: row.step, effect: row.effect, low: row.ci_low, high: row.ci_high }
}

export interface HeatCell {
  readonly step: number
  readonly effect: number | null
  readonly low: number | null
  readonly high: number | null
  readonly tested: boolean
}

/** One cell per step. Untested steps stay null so they can be hatched, never coloured. */
export function heatCells(nSteps: number, effects: readonly StepEffect[]): readonly HeatCell[] {
  const byStep = new Map(effects.map((entry) => [entry.step, entry]))
  return Array.from({ length: nSteps }, (_, index) => {
    const step = index + 1
    const row = byStep.get(step)
    if (!row) return { step, effect: null, low: null, high: null, tested: false }
    return { step, effect: row.effect, low: row.ci_low, high: row.ci_high, tested: true }
  })
}

/** Recall failure: the judge's shortlist never contained the step replay blamed. */
export function judgeMissed(
  ranking: readonly JudgeRankEntry[],
  blamedStep: number | null,
): boolean {
  if (blamedStep === null) return false
  return !ranking.some((entry) => entry.step === blamedStep)
}

export interface ForestRow {
  readonly step: number
  readonly effect: number
  readonly low: number
  readonly high: number
  /** The interval clears delta on its own. */
  readonly clears: boolean
  /** The earliest clearing step: the one blame lands on. */
  readonly blamed: boolean
}

/** One row per tested step, in step order, each marked against the blame rule. */
export function forestRows(
  effects: readonly StepEffect[],
  delta: number,
  blamedStep: number | null,
): readonly ForestRow[] {
  return [...effects]
    .sort((a, b) => a.step - b.step)
    .map((entry) => ({
      step: entry.step,
      effect: entry.effect,
      low: entry.ci_low,
      high: entry.ci_high,
      clears: clearsDelta(entry, delta),
      blamed: entry.step === blamedStep,
    }))
}

export function effectForStep(
  effects: readonly StepEffect[],
  step: number,
): StepEffect | undefined {
  return effects.find((entry) => entry.step === step)
}

/** The widest [low, high] across the tested steps, padded so no whisker touches the axis. */
export function effectDomain(
  effects: readonly StepEffect[],
  delta: number,
): readonly [number, number] {
  const bounds = effects.flatMap((entry) => [entry.ci_low, entry.ci_high])
  const candidates = [...bounds, 0, delta]
  const min = Math.min(...candidates)
  const max = Math.max(...candidates)
  const pad = Math.max((max - min) * 0.08, 0.05)
  return [Math.max(-1, min - pad), Math.min(1, max + pad)]
}
