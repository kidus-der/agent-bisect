import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { KpiRow } from './KpiRow'
import type { Kpis } from './api'

const KPIS: Kpis = {
  runs_recorded: 266,
  failures_diagnosed: 86,
  calls_spent: 86490,
  cost_per_diagnosis_usd: 1.5209,
}

describe('KpiRow', () => {
  test('renders every KPI with its final value available to assistive tech', () => {
    render(<KpiRow kpis={KPIS} />)
    // StatTicker writes the value twice: once for screen readers, once for the ticker.
    for (const value of ['266', '86', '86,490', '$1.52'])
      expect(screen.getAllByText(value).length).toBeGreaterThan(0)
  })

  test('labels each number so it is not a bare figure', () => {
    render(<KpiRow kpis={KPIS} />)
    for (const label of ['runs recorded', 'failures diagnosed', 'calls spent', 'cost per diagnosis'])
      expect(screen.getByText(label)).toBeInTheDocument()
  })

  test('shows no trend arrows, because the API reports no deltas', () => {
    const { container } = render(<KpiRow kpis={KPIS} />)
    expect(container.textContent).not.toMatch(/[▲▼]/)
  })
})
