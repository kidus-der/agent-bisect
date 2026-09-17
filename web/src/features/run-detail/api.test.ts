import { describe, expect, it } from 'vitest'

import {
  availableOrNull,
  isNotAvailable,
  normalizeRunDetail,
  normalizeStateDiff,
  normalizeStepPayload,
  runDetailKeys,
  runDetailPaths,
} from './api'

describe('runDetailPaths', () => {
  it('encodes the run id so a hostile id cannot escape the path', () => {
    // Arrange
    const runId = 'a/b?c'

    // Act
    const path = runDetailPaths.detail(runId)

    // Assert
    expect(path).toBe('/runs/a%2Fb%3Fc')
  })

  it('builds every run-scoped path from the run and step', () => {
    expect(runDetailPaths.step('r1', 7)).toBe('/runs/r1/steps/7')
    expect(runDetailPaths.interventionDiff('r1', 7)).toBe('/runs/r1/steps/7/intervention-diff')
    expect(runDetailPaths.stateDiff('r1', 7)).toBe('/runs/r1/steps/7/state-diff')
    expect(runDetailPaths.reruns('r1')).toBe('/runs/r1/reruns')
    expect(runDetailPaths.rerunSteps('r1', 'r1-t7-0')).toBe('/runs/r1/reruns/r1-t7-0/steps')
  })
})

describe('runDetailKeys', () => {
  it('keys a step query by run and step so scrubbing does not collide', () => {
    expect(runDetailKeys.step('r1', 7)).not.toEqual(runDetailKeys.step('r1', 8))
    expect(runDetailKeys.step('r1', 7)).not.toEqual(runDetailKeys.step('r2', 7))
  })
})

describe('isNotAvailable', () => {
  it('recognises the not_available payload the server sends instead of a fake number', () => {
    expect(isNotAvailable({ status: 'not_available', reason: 'no recordings yet' })).toBe(true)
  })

  it('leaves real payloads alone', () => {
    expect(isNotAvailable({ step_idx: 7, entries: [] })).toBe(false)
    expect(isNotAvailable(null)).toBe(false)
  })
})

describe('availableOrNull', () => {
  it('returns null for not_available and the payload otherwise', () => {
    const payload = { step_idx: 7, entries: [] }
    expect(availableOrNull({ status: 'not_available', reason: 'x' })).toBeNull()
    expect(availableOrNull(payload)).toBe(payload)
    expect(availableOrNull(null)).toBeNull()
  })
})

describe('normalizeRunDetail', () => {
  it('turns a payload missing its arrays into one every component can map over', () => {
    // Arrange: what a wrong-shaped 200 looks like.
    const raw = { run_id: 'r1' } as unknown as Parameters<typeof normalizeRunDetail>[0]

    // Act
    const detail = normalizeRunDetail(raw)

    // Assert
    expect(detail.steps).toEqual([])
    expect(detail.estimate).toBeNull()
    expect(detail.judge).toBeNull()
  })

  it('keeps real arrays untouched and fills only the missing ones', () => {
    const raw = {
      run_id: 'r1',
      steps: [{ step_idx: 1 }],
      estimate: { blamed_step: 7 },
      judge: { all_at_once: [{ step: 7 }] },
    } as unknown as Parameters<typeof normalizeRunDetail>[0]

    const detail = normalizeRunDetail(raw)

    expect(detail.steps).toHaveLength(1)
    expect(detail.estimate?.blamed_step).toBe(7)
    expect(detail.estimate?.step_effects).toEqual([])
    expect(detail.judge?.all_at_once).toHaveLength(1)
    expect(detail.judge?.step_by_step).toEqual([])
  })
})

describe('normalizeStepPayload', () => {
  it('always yields a messages array', () => {
    const raw = { step_idx: 3 } as unknown as Parameters<typeof normalizeStepPayload>[0]
    expect(normalizeStepPayload(raw).messages).toEqual([])
  })
})

describe('normalizeStateDiff', () => {
  it('always yields an entries array', () => {
    const raw = { step_idx: 3 } as unknown as Parameters<typeof normalizeStateDiff>[0]
    expect(normalizeStateDiff(raw)).toEqual({ step_idx: 3, entries: [] })
  })

  it('passes not_available through untouched', () => {
    const raw = { status: 'not_available', reason: 'no recordings yet' } as const
    expect(normalizeStateDiff(raw)).toBe(raw)
  })
})
