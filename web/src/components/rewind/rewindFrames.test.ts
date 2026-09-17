import { describe, expect, test } from 'vitest'

import { REWIND_STEP_COUNT, REWIND_TARGET_STEP, buildRewindFrames } from './rewindFrames'

const frames = buildRewindFrames()
const phases = frames.map((frame) => frame.phase)
const firstOf = (phase: string) => {
  const frame = frames.find((candidate) => candidate.phase === phase)
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

  test('rewind reads steps 1-6 from tape and un-runs everything after step 7', () => {
    const rewind = firstOf('rewind')
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
