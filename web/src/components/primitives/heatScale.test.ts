import { describe, expect, test } from 'vitest'

import { type HeatDatum, SCALE_STEPS, buildHeatScale, bucketVariable } from './heatScale'

/** `brief-12-step` as `/api/runs` serves it: one big effect, the rest near zero. */
const BRIEF_RUN: readonly HeatDatum[] = [
  { step: 1, effect: -0.0625 },
  { step: 2, effect: 0.125 },
  { step: 3, effect: 0.125 },
  { step: 4, effect: 0.125 },
  { step: 5, effect: 0.0625 },
  { step: 6, effect: 0.0625 },
  { step: 7, effect: 0.875 },
  { step: 8, effect: 0.25 },
  { step: 9, effect: 0.0625 },
  { step: 10, effect: 0.0625 },
  { step: 11, effect: 0.0 },
  { step: 12, effect: -0.0625 },
]
const BLAMED = 7

function bucketsFor(steps: readonly HeatDatum[], blamed?: number): number[] {
  const scale = buildHeatScale(steps, blamed)
  return steps
    .filter((entry) => entry.effect !== null && entry.step !== blamed)
    .map((entry) => scale.bucket(entry.effect as number))
}

describe('buildHeatScale on a real run', () => {
  test('separates the ordinary steps instead of flattening them into one bucket', () => {
    // The regression: with a fixed [0,1] domain the blamed +0.88 swamped the
    // rest and ten of twelve cells rendered identically.
    const distinct = new Set(bucketsFor(BRIEF_RUN, BLAMED))
    expect(distinct.size).toBeGreaterThanOrEqual(3)
  })

  test('builds its domain from the tested steps that are not blamed', () => {
    expect(buildHeatScale(BRIEF_RUN, BLAMED).domain).toEqual([-0.0625, 0.25])
  })

  test('keeps a negative effect below a zero one', () => {
    const scale = buildHeatScale(BRIEF_RUN, BLAMED)
    expect(scale.bucket(-0.0625)).toBeLessThan(scale.bucket(0))
  })

  test('orders the ramp: a larger effect is never a lower bucket', () => {
    const scale = buildHeatScale(BRIEF_RUN, BLAMED)
    const ordered = [-0.0625, 0, 0.0625, 0.125, 0.25].map((effect) => scale.bucket(effect))
    for (let index = 1; index < ordered.length; index += 1) {
      expect(ordered[index]).toBeGreaterThanOrEqual(ordered[index - 1] ?? 0)
    }
  })

  test('puts the largest non-blamed effect at the top of the ramp', () => {
    expect(buildHeatScale(BRIEF_RUN, BLAMED).bucket(0.25)).toBe(SCALE_STEPS)
  })

  test('would still flatten if the blamed step were left in the domain', () => {
    // Guards the reason the exclusion exists.
    const withBlamed = new Set(
      BRIEF_RUN.filter((entry) => entry.step !== BLAMED).map((entry) =>
        buildHeatScale(BRIEF_RUN).bucket(entry.effect as number),
      ),
    )
    expect(withBlamed.size).toBeLessThan(3)
  })
})

describe('buildHeatScale edge cases', () => {
  test('uses one middle bucket when every tested step measured the same', () => {
    const flat: readonly HeatDatum[] = [
      { step: 1, effect: 0.1 },
      { step: 2, effect: 0.1 },
    ]
    expect(new Set(bucketsFor(flat))).toEqual(new Set([3]))
  })

  test('survives a run where only the blamed step was tested', () => {
    const onlyBlamed: readonly HeatDatum[] = [
      { step: 1, effect: null },
      { step: 2, effect: 0.9 },
    ]
    const scale = buildHeatScale(onlyBlamed, 2)
    expect(scale.domain).toBeNull()
    expect(scale.bucket(0.9)).toBe(3)
  })

  test('survives a run with nothing tested at all', () => {
    expect(buildHeatScale([{ step: 1, effect: null }]).domain).toBeNull()
  })
})

describe('bucketVariable', () => {
  test('maps a bucket to its scale token', () => {
    expect(bucketVariable(1)).toBe('var(--chart-scale-01)')
    expect(bucketVariable(SCALE_STEPS)).toBe(`var(--chart-scale-0${SCALE_STEPS})`)
  })

  test('clamps a bucket that fell outside the ramp', () => {
    expect(bucketVariable(0)).toBe('var(--chart-scale-01)')
    expect(bucketVariable(99)).toBe(`var(--chart-scale-0${SCALE_STEPS})`)
  })
})
