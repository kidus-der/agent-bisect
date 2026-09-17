import { describe, expect, test } from 'vitest'

import {
  REWIND_STEP_COUNT,
  REWIND_TARGET_STEP,
  type RewindSpec,
  buildRewindFrames,
} from './rewindFrames'

const frames = buildRewindFrames()
const phases = frames.map((frame) => frame.phase)
const firstOf = (phase: string) => {
  const frame = frames.find((candidate) => candidate.phase === phase)
  if (!frame) throw new Error(`no ${phase} frame`)
  return frame
}
const lastOf = (phase: string) => {
  const frame = frames.findLast((candidate) => candidate.phase === phase)
  if (!frame) throw new Error(`no ${phase} frame`)
  return frame
}

describe('rewind frames', () => {
  test('tell the story in order: record, fail, rewind, intervene, replay, pass, verdict', () => {
    const order = phases.filter((phase, index) => phase !== phases[index - 1])
    expect(order).toEqual(['record', 'fail', 'rewind', 'intervene', 'replay', 'pass', 'verdict'])
  })

  test('every frame describes all 12 steps', () => {
    frames.forEach((frame) => expect(frame.steps).toHaveLength(REWIND_STEP_COUNT))
  })

  test('recording runs one live step at a time, then step 12 fails', () => {
    const recording = frames.filter((frame) => frame.phase === 'record')
    expect(recording).toHaveLength(REWIND_STEP_COUNT)
    recording.forEach((frame) =>
      expect(frame.steps.filter((state) => state === 'live')).toHaveLength(1),
    )
    expect(firstOf('fail').steps.at(-1)).toBe('failed')
  })

  test('the rewind sweeps steps back to tape one at a time, left to right', () => {
    const rewind = frames.filter((frame) => frame.phase === 'rewind')
    expect(rewind).toHaveLength(REWIND_TARGET_STEP - 1)
    expect(rewind.map((frame) => frame.rewoundThrough)).toEqual([1, 2, 3, 4, 5, 6])
    expect(firstOf('rewind').steps.filter((state) => state === 'tape')).toHaveLength(1)
  })

  test('the settled rewind reads steps 1-6 from tape and un-runs everything after step 7', () => {
    const rewind = lastOf('rewind')
    expect(rewind.playhead).toBe(REWIND_TARGET_STEP)
    expect(rewind.steps.slice(0, 6)).toEqual(Array(6).fill('tape'))
    expect(rewind.steps.slice(7)).toEqual(Array(5).fill('pending'))
    expect(rewind.status).toContain('0 calls')
  })

  test('the intervention names both values and only step 7 is blamed', () => {
    const intervene = firstOf('intervene')
    expect(intervene.status).toContain('NM1VX1 → ZFA04Y')
    expect(intervene.steps.filter((state) => state === 'blamed')).toHaveLength(1)
    expect(intervene.steps[REWIND_TARGET_STEP - 1]).toBe('blamed')
  })

  test('replay re-runs steps 8-12 only; tape steps are never re-run', () => {
    const replay = frames.filter((frame) => frame.phase === 'replay')
    expect(replay.map((frame) => frame.playhead)).toEqual([8, 9, 10, 11, 12])
    replay.forEach((frame) => expect(frame.steps.slice(0, 6)).toEqual(Array(6).fill('tape')))
  })

  test('the final frame is the verdict: pass, with step 7 blamed', () => {
    const last = frames.at(-1)
    expect(last?.phase).toBe('verdict')
    expect(last?.steps.at(-1)).toBe('passed')
    expect(last?.status).toBe('blame: step 7')
  })
})

describe('rewind frames for a real run', () => {
  const SPEC: RewindSpec = {
    stepCount: 5,
    targetStep: 3,
    reruns: 16,
    intervention: { field: 'origin', before: 'JFK', after: 'LGA' },
    verdict: { step: 3, effect: 0.5, low: 0.2, high: 0.7 },
  }
  const real = buildRewindFrames(SPEC)

  test('follows the run it was given rather than the illustration', () => {
    real.forEach((frame) => expect(frame.steps).toHaveLength(SPEC.stepCount))
    expect(real.filter((frame) => frame.phase === 'rewind')).toHaveLength(SPEC.targetStep - 1)
    expect(real.filter((frame) => frame.phase === 'replay').map((frame) => frame.playhead)).toEqual([
      4, 5,
    ])
  })

  test('names the replaced field and both values, and the re-run count', () => {
    const intervene = real.find((frame) => frame.phase === 'intervene')
    expect(intervene?.status).toBe('step 3 · tool result replaced · origin JFK → LGA')
    expect(real.find((frame) => frame.phase === 'replay')?.status).toContain('× 16')
  })

  test('still describes the intervention when the API served no diff for it', () => {
    const [intervene] = buildRewindFrames({ ...SPEC, intervention: null }).filter(
      (frame) => frame.phase === 'intervene',
    )
    expect(intervene?.status).toBe('step 3 · tool result replaced')
  })

  test('keeps a long run’s recording pass from outlasting the rest of the loop', () => {
    const long = buildRewindFrames({ ...SPEC, stepCount: 60, targetStep: 55 })
    const recording = long.filter((frame) => frame.phase === 'record')
    const total = recording.reduce((sum, frame) => sum + frame.holdMs, 0)
    expect(total).toBeLessThanOrEqual(4000)
  })
})
