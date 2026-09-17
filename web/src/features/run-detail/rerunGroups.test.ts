import { describe, expect, it } from 'vitest'

import type { RerunRow } from './api'
import { BATCH_SIZE, batchesOf, groupReruns } from './rerunGroups'

function row(arm: RerunRow['arm'], step: number, index: number, passed: boolean): RerunRow {
  return {
    rerun_id: `r-${arm}${step}-${index}`,
    arm,
    step,
    seed: 100 + index,
    passed,
    n_steps: 12,
    calls: 10,
  }
}

const ROWS: readonly RerunRow[] = [
  row('treated', 7, 0, true),
  row('treated', 7, 1, true),
  row('treated', 3, 0, false),
  row('control', 1, 0, false),
  row('control', 1, 1, true),
]

describe('groupReruns', () => {
  it('puts the control arm first, then the treated steps in order', () => {
    // Act
    const groups = groupReruns(ROWS)

    // Assert
    expect(groups.map((group) => `${group.arm}-${group.step}`)).toEqual([
      'control-1',
      'treated-3',
      'treated-7',
    ])
  })

  it('counts the passes in each arm', () => {
    const groups = groupReruns(ROWS)

    expect(groups[0]).toMatchObject({ passed: 1, arm: 'control' })
    expect(groups[2]).toMatchObject({ passed: 2, arm: 'treated' })
  })

  it('marks a single control arm as shared by every treated step', () => {
    const groups = groupReruns(ROWS)

    expect(groups[0]?.shared).toBe(true)
    expect(groups[1]?.shared).toBe(false)
  })

  it('does not call a per-step control arm shared', () => {
    const perStep = [row('control', 3, 0, false), row('control', 7, 0, false), ...ROWS.slice(0, 3)]

    expect(groupReruns(perStep).every((group) => !group.shared)).toBe(true)
  })

  it('keeps the re-runs of a group in the order the sampler produced them', () => {
    const groups = groupReruns(ROWS)

    expect(groups[2]?.rows.map((entry) => entry.rerun_id)).toEqual(['r-treated7-0', 'r-treated7-1'])
  })

  it('returns nothing for a run with no re-runs', () => {
    expect(groupReruns([])).toEqual([])
  })
})

describe('batchesOf', () => {
  it('splits into the sequential estimator batch size, last batch short', () => {
    const rows = Array.from({ length: 6 }, (_, index) => row('treated', 7, index, true))

    const batches = batchesOf(rows, BATCH_SIZE)

    expect(batches.map((batch) => batch.length)).toEqual([4, 2])
  })

  it('returns nothing for an empty arm', () => {
    expect(batchesOf([], BATCH_SIZE)).toEqual([])
  })
})
