import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { buildHeatScale } from '@/components/primitives/heatScale'

import { BlameHeatStripe } from './BlameHeatStripe'
import type { HeatCell } from './blame'
import { timelineGeometry } from './timelineScale'

/** The brief run's real effects: ten ordinary steps and one blamed +0.88. */
const BRIEF_EFFECTS = [
  -0.0625, 0.125, 0.125, 0.125, 0.0625, 0.0625, 0.875, 0.25, 0.0625, 0.0625, 0, -0.0625,
]

const CELLS: readonly HeatCell[] = BRIEF_EFFECTS.map((effect, index) => ({
  step: index + 1,
  effect,
  low: effect - 0.2,
  high: effect + 0.2,
  tested: true,
}))

function bucketsOf(cells: readonly HeatCell[], blamedStep: number | null): Set<string> {
  const { container } = render(
    <BlameHeatStripe
      cells={cells}
      geometry={timelineGeometry({ nSteps: cells.length, availableWidth: 800 })}
      blamedStep={blamedStep}
      scale={buildHeatScale(cells, blamedStep ?? undefined)}
      height={14}
    />,
  )
  const fills = [...container.querySelectorAll('[data-state="tested"]')].map(
    (rect) => rect.getAttribute('fill') ?? '',
  )
  return new Set(fills)
}

describe('BlameHeatStripe ramp', () => {
  it('separates ordinary effects instead of collapsing them under the blamed step', () => {
    // Arrange / Act: the blamed +0.88 must not swamp the −0.06…+0.25 spread.
    const buckets = bucketsOf(CELLS, 7)

    // Assert
    expect(buckets.size).toBeGreaterThanOrEqual(3)
  })

  it('keeps the blamed cell out of the ramp, on its own gradient', () => {
    const { container } = render(
      <BlameHeatStripe
        cells={CELLS}
        geometry={timelineGeometry({ nSteps: CELLS.length, availableWidth: 800 })}
        blamedStep={7}
        scale={buildHeatScale(CELLS, 7)}
        height={14}
      />,
    )
    const blamed = container.querySelector('[data-state="blamed"]')
    expect(blamed?.getAttribute('fill')).toMatch(/^url\(#/)
  })

  it('hatches an untested step rather than giving it a bucket', () => {
    const cells = CELLS.map((cell, index) =>
      index === 2 ? { ...cell, effect: null, low: null, high: null, tested: false } : cell,
    )
    const { container } = render(
      <BlameHeatStripe
        cells={cells}
        geometry={timelineGeometry({ nSteps: cells.length, availableWidth: 800 })}
        blamedStep={7}
        scale={buildHeatScale(cells, 7)}
        height={14}
      />,
    )
    expect(container.querySelector('[data-state="untested"]')?.getAttribute('fill')).toMatch(
      /^url\(#/,
    )
  })
})
