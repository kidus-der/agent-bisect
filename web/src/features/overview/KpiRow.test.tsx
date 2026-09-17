import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { KpiRow } from './KpiRow'
import type { Kpis } from './api'

const KPIS: Kpis = {
  runs_recorded: 266,
  failures_diagnosed: 86,
  calls_spent: 86490,
  cost_per_diagnosis_calls: 1005.7,
  cost_per_diagnosis_usd: 1.5209,
}

/** Real mode: no price list, and nothing diagnosed yet. */
const UNPRICED: Kpis = { ...KPIS, cost_per_diagnosis_usd: null }
const UNDIAGNOSED: Kpis = { ...UNPRICED, cost_per_diagnosis_calls: null, failures_diagnosed: 0 }

describe('KpiRow', () => {
  test('renders every KPI with its final value available to assistive tech', () => {
    render(<KpiRow kpis={KPIS} />)
    // StatTicker writes the value twice: once for screen readers, once for the ticker.
    for (const value of ['266', '86', '86,490', '1,006'])
      expect(screen.getAllByText(value).length).toBeGreaterThan(0)
  })

  test('labels each number so it is not a bare figure', () => {
    render(<KpiRow kpis={KPIS} />)
    for (const label of [
      'runs recorded',
      'failures diagnosed',
      'calls spent',
      'cost per diagnosis',
    ])
      expect(screen.getByText(label)).toBeInTheDocument()
  })

  test('states the cost in calls, and adds the price only when there is one', () => {
    // Arrange / Act / Assert — calls are always measured; USD needs a price
    // list that real mode does not have.
    const priced = render(<KpiRow kpis={KPIS} />)
    expect(priced.container.textContent).toContain('$1.52')
    priced.unmount()

    const unpriced = render(<KpiRow kpis={UNPRICED} />)
    expect(unpriced.container.textContent).not.toContain('$')
    expect(unpriced.container.textContent).toContain('model calls')
  })

  test('shows a dash, not a zero, when nothing has been diagnosed yet', () => {
    render(<KpiRow kpis={UNDIAGNOSED} />)
    const cost = screen.getByText('cost per diagnosis').closest('div')
    expect(cost?.textContent).toContain('—')
    expect(cost?.textContent).not.toContain('0.00')
  })

  test('shows no trend arrows, because the API reports no deltas', () => {
    const { container } = render(<KpiRow kpis={KPIS} />)
    expect(container.textContent).not.toMatch(/[▲▼]/)
  })
})
