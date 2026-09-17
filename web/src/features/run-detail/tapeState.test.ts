import { describe, expect, it } from 'vitest'

import { type TapeModel, nextRewind, tapeStepStates } from './tapeState'

const BASE: TapeModel = {
  nSteps: 5,
  playhead: 5,
  outcome: 'fail',
  blamedStep: null,
  rewind: null,
}

describe('tapeStepStates, the recording', () => {
  it('never calls a recorded step pending, wherever the playhead sits', () => {
    // Arrange / Act
    const states = tapeStepStates({ ...BASE, playhead: 3 })

    // Assert
    expect(states).toEqual(['ran', 'ran', 'ran', 'ran', 'failed'])
  })

  it('ends on the recorded outcome', () => {
    expect(tapeStepStates({ ...BASE, playhead: 5 }).at(-1)).toBe('failed')
    expect(tapeStepStates({ ...BASE, playhead: 5, outcome: 'pass' }).at(-1)).toBe('passed')
  })

  it('leaves the last step neutral when the run is still recording', () => {
    expect(tapeStepStates({ ...BASE, playhead: 5, outcome: null }).at(-1)).toBe('ran')
  })

  it('marks the blamed step on the tape before any rewind is played', () => {
    expect(tapeStepStates({ ...BASE, blamedStep: 3 })).toEqual([
      'ran',
      'ran',
      'blamed',
      'ran',
      'failed',
    ])
  })
})

describe('tapeStepStates, after a rewind to k', () => {
  const rewound = (
    phase: 'rewinding' | 'intervened' | 'replaying' | 'settled',
    replayedThrough: number,
    passed: boolean | null = null,
  ): TapeModel => ({
    ...BASE,
    playhead: 3,
    rewind: { step: 3, phase, replayedThrough, passed },
  })

  it('bands the steps before k as read from tape', () => {
    expect(tapeStepStates(rewound('rewinding', 3)).slice(0, 2)).toEqual(['tape', 'tape'])
  })

  it('does not blame step k until the intervention is applied', () => {
    expect(tapeStepStates(rewound('rewinding', 3))[2]).toBe('ran')
    expect(tapeStepStates(rewound('intervened', 3))[2]).toBe('blamed')
  })

  it('replays the tail one step at a time, the leading edge live', () => {
    // Arrange / Act: steps 4 has replayed, step 5 is running now.
    const states = tapeStepStates(rewound('replaying', 4))

    // Assert
    expect(states).toEqual(['tape', 'tape', 'blamed', 'ran', 'live'])
  })

  it('ends on the re-run outcome, which is a real recorded result', () => {
    expect(tapeStepStates(rewound('settled', 5, true))).toEqual([
      'tape',
      'tape',
      'blamed',
      'ran',
      'passed',
    ])
    expect(tapeStepStates(rewound('settled', 5, false)).at(-1)).toBe('failed')
  })

  it('leaves the tail neutral when the re-run outcome is unknown', () => {
    expect(tapeStepStates(rewound('settled', 5, null)).at(-1)).toBe('ran')
  })

  it('handles a rewind to the last step, where there is no tail to replay', () => {
    const states = tapeStepStates({
      ...BASE,
      rewind: { step: 5, phase: 'settled', replayedThrough: 5, passed: true },
    })
    expect(states).toEqual(['tape', 'tape', 'tape', 'tape', 'blamed'])
  })
})

describe('nextRewind', () => {
  it('walks rewinding -> intervened -> replaying one step at a time -> settled', () => {
    const start = { step: 3, phase: 'rewinding' as const, replayedThrough: 3, passed: null }
    const a = nextRewind(start, 5)
    const b = nextRewind(a, 5)
    const c = nextRewind(b, 5)
    const d = nextRewind(c, 5)

    expect(a.phase).toBe('intervened')
    expect(b).toMatchObject({ phase: 'replaying', replayedThrough: 4 })
    expect(c).toMatchObject({ phase: 'replaying', replayedThrough: 5 })
    expect(d.phase).toBe('settled')
    expect(nextRewind(d, 5)).toBe(d)
  })

  it('settles straight away when k is the last step', () => {
    const start = { step: 5, phase: 'intervened' as const, replayedThrough: 5, passed: null }
    expect(nextRewind(start, 5).phase).toBe('settled')
  })
})
