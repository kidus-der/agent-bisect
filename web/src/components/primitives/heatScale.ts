/**
 * The bucket scale behind a blame heat stripe.
 *
 * The naive version mapped a raw effect in [0, 1] onto five fixed buckets. Real
 * runs do not use that range: on `brief-12-step` the blamed step measures +0.88
 * while every other tested step sits between −0.06 and +0.25, so ten of twelve
 * cells landed in the bottom bucket and the stripe encoded nothing but
 * tested/blamed/untested.
 *
 * So the ramp is built from the tested effects *excluding the blamed step* —
 * the blamed cell has its own amber→coral treatment and would otherwise stretch
 * the domain until nothing else varied. Negative effects are part of the domain,
 * so "fixing this made it worse" is distinguishable from "no effect".
 */

export const SCALE_STEPS = 5

export interface HeatDatum {
  readonly step: number
  readonly effect: number | null
}

export interface HeatScale {
  /** 1-based bucket for a tested, non-blamed effect. */
  readonly bucket: (effect: number) => number
  /** The effects the ramp was built from; empty when nothing else was tested. */
  readonly domain: readonly [number, number] | null
}

const MIDDLE_BUCKET = Math.ceil(SCALE_STEPS / 2)

function testedEffects(steps: readonly HeatDatum[], blamedStep: number | undefined): number[] {
  return steps
    .filter((entry) => entry.effect !== null && entry.step !== blamedStep)
    .map((entry) => entry.effect as number)
}

/**
 * A scale over the steps that are not the blamed one. With fewer than two
 * distinct values there is no spread to show, so every cell takes the middle
 * bucket rather than implying a gradient that was never measured.
 */
export function buildHeatScale(steps: readonly HeatDatum[], blamedStep?: number): HeatScale {
  const effects = testedEffects(steps, blamedStep)
  if (effects.length === 0) return { bucket: () => MIDDLE_BUCKET, domain: null }

  const low = Math.min(...effects)
  const high = Math.max(...effects)
  if (low === high) return { bucket: () => MIDDLE_BUCKET, domain: [low, high] }

  const span = high - low
  return {
    domain: [low, high],
    bucket: (effect) => {
      const position = (effect - low) / span
      const index = Math.floor(position * SCALE_STEPS) + 1
      return Math.min(SCALE_STEPS, Math.max(1, index))
    },
  }
}

/** The CSS variable for a bucket, so the ramp stays a token, not a literal. */
export function bucketVariable(bucket: number): string {
  return `var(--chart-scale-0${Math.min(SCALE_STEPS, Math.max(1, bucket))})`
}
