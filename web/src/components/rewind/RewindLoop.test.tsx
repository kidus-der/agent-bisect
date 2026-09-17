import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { RewindLoop } from './RewindLoop'

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
