import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { RewindLoop } from './RewindLoop'
import type { RewindSpec } from './rewindFrames'

const TICK_MS = 50
const MAX_TICKS = 600

/** The loop wraps, so a fixed delay would land anywhere; creep forward until the phase arrives. */
function advanceToVerdict(): void {
  for (let tick = 0; tick < MAX_TICKS; tick += 1) {
    if (screen.getByTestId('rewind-loop').getAttribute('data-phase') === 'verdict') return
    act(() => void vi.advanceTimersByTime(TICK_MS))
  }
  throw new Error('the rewind loop never reached its verdict')
}

const REAL_RUN: RewindSpec = {
  stepCount: 5,
  targetStep: 3,
  reruns: 16,
  intervention: { field: null, before: 'NM1VX1', after: 'ZFA04Y' },
  verdict: { step: 3, effect: 0.88, low: 0.47, high: 0.97 },
}

/** Full-motion file: the loop only advances while it is on screen. */
class VisibleObserver {
  private readonly callback: IntersectionObserverCallback
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
  }
  observe(target: Element): void {
    this.callback(
      [{ isIntersecting: true, target } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    )
  }
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return []
  }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('RewindLoop (full motion)', () => {
  test('is labelled an illustration and fully described for assistive tech', () => {
    render(<RewindLoop />)
    expect(screen.getByText(/rewind · illustration/)).toBeInTheDocument()
    expect(screen.getByText(/Illustration of one bisect/)).toHaveClass('sr-only')
    expect(screen.getByTestId('rewind-loop')).toHaveAttribute('aria-hidden', 'true')
  })

  test('stays on its first frame while offscreen', () => {
    render(<RewindLoop />)
    act(() => void vi.advanceTimersByTime(5000))
    expect(screen.getByTestId('rewind-loop')).toHaveAttribute('data-phase', 'record')
    expect(screen.getByText('recording live · step 1 of 12')).toBeInTheDocument()
  })

  test('advances when visible, and the pause button stops it', () => {
    vi.stubGlobal('IntersectionObserver', VisibleObserver)
    render(<RewindLoop />)
    act(() => void vi.advanceTimersByTime(200))
    expect(screen.getByText('recording live · step 2 of 12')).toBeInTheDocument()

    act(() => screen.getByRole('button', { name: 'Pause' }).click())
    act(() => void vi.advanceTimersByTime(5000))
    expect(screen.getByText('recording live · step 2 of 12')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('RewindLoop driven by a real run', () => {
  test('plays the run it was given and names it in the text alternative', () => {
    render(<RewindLoop spec={REAL_RUN} label="rewind · brief-12-step" runLabel="Run brief-12-step" />)
    expect(screen.getByText(/Run brief-12-step: a 5-step run/)).toHaveClass('sr-only')
    expect(screen.getByText(/re-run live 16 times/)).toBeInTheDocument()
  })

  test('reaches the verdict with the measured effect and its interval', () => {
    vi.stubGlobal('IntersectionObserver', VisibleObserver)
    render(<RewindLoop spec={REAL_RUN} />)
    advanceToVerdict()
    expect(screen.getByTestId('rewind-loop')).toHaveAttribute('data-phase', 'verdict')
    expect(screen.getByText('+0.88')).toBeInTheDocument()
    expect(screen.getByText('[+0.47, +0.97]')).toBeInTheDocument()
  })

  test('never shows blame as a bare step when no effect was reported', () => {
    vi.stubGlobal('IntersectionObserver', VisibleObserver)
    const spec = { ...REAL_RUN, verdict: null }
    render(<RewindLoop spec={spec} />)
    advanceToVerdict()
    expect(screen.getByText('decisive step 3 · no effect reported')).toBeInTheDocument()
    expect(screen.queryByText(/^\+0\./)).toBeNull()
  })
})
