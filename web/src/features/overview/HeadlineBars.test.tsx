import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { HeadlineBars } from './HeadlineBars'
import type { HeadlineResult } from './api'

const HEADLINE: HeadlineResult = {
  bisect: { value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 },
  best_judge: { value: 0.8721, ci_low: 0.7853, ci_high: 0.9271 },
  best_judge_method: 'judge_step_by_step',
  gap: { value: 0.1512, ci_low: 0.0581, ci_high: 0.2442 },
}

describe('HeadlineBars', () => {
  test('names both methods as headings', () => {
    render(<HeadlineBars headline={HEADLINE} simulated={false} />)
    expect(screen.getByRole('heading', { name: 'Bisect' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Judge · step by step' })).toBeInTheDocument()
  })

  test('states the gap in percentage points', () => {
    render(<HeadlineBars headline={HEADLINE} simulated={false} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/\+15\.1 pts/)
  })

  test('shows the gap\u2019s own paired interval and whether it clears zero', () => {
    render(<HeadlineBars headline={HEADLINE} simulated={false} />)
    expect(screen.getByText('+5.8 pts to +24.4 pts')).toBeInTheDocument()
    expect(screen.getByText(/which clears zero/)).toBeInTheDocument()
  })

  test('does not claim a gap clears zero when its interval straddles it', () => {
    render(
      <HeadlineBars
        headline={{ ...HEADLINE, gap: { value: 0.02, ci_low: -0.04, ci_high: 0.08 } }}
        simulated={false}
      />,
    )
    expect(screen.getByText(/which does not clear zero/)).toBeInTheDocument()
  })

  test('shows each estimate with its own 95% interval', () => {
    render(<HeadlineBars headline={HEADLINE} simulated={false} />)
    expect(screen.getByText('95% CI 90.2% – 98.8%')).toBeInTheDocument()
    expect(screen.getByText('95% CI 78.5% – 92.7%')).toBeInTheDocument()
  })

  test('admits simulated data in the hero when the API is serving fixtures', () => {
    const { rerender } = render(<HeadlineBars headline={HEADLINE} simulated />)
    expect(screen.getByText(/numbers are simulated/i)).toBeInTheDocument()
    rerender(<HeadlineBars headline={HEADLINE} simulated={false} />)
    expect(screen.queryByText(/numbers are simulated/i)).toBeNull()
  })

  test('reports the sample size the accuracy was scored on when it is known', () => {
    render(<HeadlineBars headline={HEADLINE} simulated={false} sampleSize={86} />)
    expect(screen.getByText(/n=86/)).toBeInTheDocument()
  })

  test('omits the sample size rather than guessing one', () => {
    render(<HeadlineBars headline={HEADLINE} simulated={false} sampleSize={null} />)
    expect(screen.queryByText(/n=/)).toBeNull()
  })
})
