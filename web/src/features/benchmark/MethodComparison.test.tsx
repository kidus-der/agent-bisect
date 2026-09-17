import { render, screen, within } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import type { MethodResult } from './api'
import { MethodComparison } from './MethodComparison'

const METHODS: readonly MethodResult[] = [
  {
    method: 'bisect',
    accuracy: { value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 },
    mean_cost_usd: 1.5607,
    mean_calls: 780.35,
  },
  {
    method: 'judge_step_by_step',
    accuracy: { value: 0.8721, ci_low: 0.7853, ci_high: 0.9271 },
    mean_cost_usd: 0.5937,
    mean_calls: 19.79,
  },
  {
    method: 'no_control',
    accuracy: { value: 0.7791, ci_low: 0.6805, ci_high: 0.8538 },
    mean_cost_usd: 1.4912,
    mean_calls: 745.58,
  },
]

describe('MethodComparison', () => {
  test('never shows an estimate without its interval', () => {
    // Arrange / Act
    render(<MethodComparison methods={METHODS} />)

    // Assert — one interval per method, beside each accuracy.
    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(METHODS.length)
    for (const row of rows) {
      expect(within(row).getByText(/\[\d+\.\d%,\s\d+\.\d%\]/)).toBeInTheDocument()
    }
  })

  test('formats the interval bounds as percentages to one decimal', () => {
    // Act
    render(<MethodComparison methods={METHODS} />)

    // Assert
    expect(screen.getByText('[90.2%, 98.8%]')).toBeInTheDocument()
    expect(screen.getByText('[78.5%, 92.7%]')).toBeInTheDocument()
  })

  test('labels every interval for a screen reader', () => {
    // Act
    render(<MethodComparison methods={METHODS} />)

    // Assert
    expect(screen.getAllByText('95% bootstrap interval')).toHaveLength(METHODS.length)
  })

  test('shows the mean cost and calls beside each method', () => {
    // Act
    render(<MethodComparison methods={METHODS} />)

    // Assert
    expect(screen.getByText('$1.56')).toBeInTheDocument()
    expect(screen.getByText('780 calls')).toBeInTheDocument()
  })

  test('reports an unattainable pre-registered bar as not met, at its real value', () => {
    // Arrange — best judge 87.2% + 15 points is 102.2%.
    render(<MethodComparison methods={METHODS} />)

    // Assert
    expect(screen.getByText(/not met · 102\.2%/)).toBeInTheDocument()
    expect(screen.getByText(/lands above 100%/)).toBeInTheDocument()
  })

  test('reports a cleared bar when Bisect reaches it', () => {
    // Arrange
    const reachable: readonly MethodResult[] = [
      METHODS[0] as MethodResult,
      {
        method: 'judge_all_at_once',
        accuracy: { value: 0.5, ci_low: 0.4, ci_high: 0.6 },
        mean_cost_usd: 0.03,
        mean_calls: 1,
      },
    ]

    // Act
    render(<MethodComparison methods={reachable} />)

    // Assert
    expect(screen.getByText(/met · 65\.0%/)).toBeInTheDocument()
  })

  test('states Bisect’s margin over the best judge', () => {
    render(<MethodComparison methods={METHODS} />)
    expect(screen.getByText('+9.3 pts')).toBeInTheDocument()
  })
})
