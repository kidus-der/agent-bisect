import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { StatTicker } from '@/components/primitives/StatTicker'
import { stubMatchMedia } from '@/test/setup'

import { RewindLoop } from './RewindLoop'

// Motion caches prefers-reduced-motion per module graph, so reduced-motion cases get their own file.
stubMatchMedia((query) => query.includes('prefers-reduced-motion'))

describe('reduced motion', () => {
  test('RewindLoop shows the final state immediately, with no pause control', () => {
    render(<RewindLoop />)
    expect(screen.getByTestId('rewind-loop')).toHaveAttribute('data-phase', 'verdict')
    expect(screen.getByText('+0.75')).toBeInTheDocument()
    expect(screen.getByText('[+0.41, +0.94]')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
  })

  test('StatTicker writes its final value at once instead of counting', () => {
    const { container } = render(<StatTicker label="effect" value={0.75} decimals={2} signed />)
    expect(container.querySelector('[aria-hidden="true"].num')).toHaveTextContent('+0.75')
  })
})
