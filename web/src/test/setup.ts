import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

/** jsdom has no layout engine; these stubs are what motion, radix and the virtualizer probe for. */
class ObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return []
  }
}

// Assigned directly (not vi.stubGlobal) so a test's vi.unstubAllGlobals() cannot remove them.
Object.assign(globalThis, { ResizeObserver: ObserverStub, IntersectionObserver: ObserverStub })

export function stubMatchMedia(matches: (query: string) => boolean): void {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: matches(query),
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })
}

stubMatchMedia(() => false)
Element.prototype.scrollIntoView = () => undefined
window.scrollTo = () => undefined
