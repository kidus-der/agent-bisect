import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { StatTicker } from './StatTicker'

describe('StatTicker', () => {
  test('announces the final value once; the animated digits are hidden from assistive tech', () => {
    const { container } = render(
      <StatTicker label="cost" value={3.36} decimals={2} prefix="$" caption="this bisect" />,
    )
    expect(screen.getByText('$3.36', { selector: '.sr-only' })).toBeInTheDocument()
    expect(container.querySelector('.num')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByText('this bisect')).toBeInTheDocument()
  })

  test('uses tabular mono numerals and an instrument label', () => {
    const { container } = render(<StatTicker label="re-runs" value={8} />)
    expect(container.querySelector('.num')).toHaveClass('text-stat')
    expect(screen.getByText('re-runs')).toHaveClass('label-instrument')
  })
})
