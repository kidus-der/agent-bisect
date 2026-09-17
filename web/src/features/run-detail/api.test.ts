import { describe, expect, it } from 'vitest'

import { availableOrNull, isNotAvailable, runDetailKeys, runDetailPaths } from './api'

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
