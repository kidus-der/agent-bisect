import { describe, expect, it } from 'vitest'

import { forkCellState, forkLabel, rerunSummary, tapePrefixClause } from './rerunNarrative'

describe('forkLabel', () => {
  it('says an intervention was applied on the treated arm', () => {
    expect(forkLabel('treated')).toBe('fork · intervention applied here')
  })

  it('never claims an intervention on the control arm', () => {
    // The control arm is defined by nothing being replaced. Saying otherwise
    // contradicts the one claim the product makes.
    expect(forkLabel('control')).toBe('fork · control · nothing replaced')
  })
})

describe('forkCellState', () => {
  it('marks the treated fork as the blamed, intervened cell', () => {
    expect(forkCellState('treated')).toBe('blamed')
  })

  it('leaves the control fork unblamed, because amber means blame', () => {
    expect(forkCellState('control')).toBe('ran')
  })
})

describe('rerunSummary', () => {
  it('attributes a treated difference to the intervention', () => {
    expect(rerunSummary('treated', 7, 0)).toMatch(/Only the intervention at step 7 differs/)
    expect(rerunSummary('treated', 7, 2)).toMatch(/2 steps after the fork came out differently/)
  })

  it('attributes a control difference to the seed, never to an intervention', () => {
    const summary = rerunSummary('control', 1, 0)

    expect(summary).toMatch(/replaced nothing/)
    expect(summary).toMatch(/only by its seed/)
    expect(summary).not.toMatch(/intervention/)
  })

  it('still counts what the control seed changed', () => {
    expect(rerunSummary('control', 1, 3)).toMatch(/3 steps after the fork came out differently/)
  })

  it('uses the singular for one changed step', () => {
    expect(rerunSummary('treated', 7, 1)).toMatch(/1 step after the fork came out differently/)
  })
})

describe('tapePrefixClause', () => {
  it('describes the replayed prefix', () => {
    expect(tapePrefixClause(7)).toBe('steps 1–6 read from tape · 0 calls')
  })

  it('uses the singular for a one-step prefix', () => {
    expect(tapePrefixClause(2)).toBe('step 1 read from tape · 0 calls')
  })

  it('never writes an empty range when the fork is the first step', () => {
    // A control forking at k=1 replays nothing: "steps 1–0" is not a range.
    expect(tapePrefixClause(1)).toBe('nothing read from tape · live from step 1')
  })
})
