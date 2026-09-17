import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { HeatLegend } from './HeatLegend'
import { SCALE_STEPS } from './heatScale'
import { formatEffect } from '@/lib/format'

describe('HeatLegend', () => {
  test('prints the ramp’s real range when one stripe is being explained', () => {
    render(<HeatLegend domain={[-0.0625, 0.25]} format={formatEffect} />)
    expect(screen.getByText('effect −0.06 … +0.25')).toBeInTheDocument()
  })

  test('says the scale is per run when several stripes share the view', () => {
    // Each stripe builds its own domain, so equal colours across rows do not
    // mean equal effects — printing one range would claim otherwise.
    render(<HeatLegend perRun domain={[-0.0625, 0.25]} format={formatEffect} />)
    expect(screen.getByText('effect · scaled per run')).toBeInTheDocument()
    expect(screen.queryByText(/…/)).toBeNull()
  })

  test('falls back to the per-run wording when no domain was measured', () => {
    render(<HeatLegend domain={null} format={formatEffect} />)
    expect(screen.getByText('effect · scaled per run')).toBeInTheDocument()
  })

  test('names the two treatments that sit outside the ramp', () => {
    render(<HeatLegend perRun format={formatEffect} />)
    expect(screen.getByText('blamed')).toBeInTheDocument()
    expect(screen.getByText('untested')).toBeInTheDocument()
  })

  test('shows one swatch per ramp step', () => {
    const { container } = render(<HeatLegend perRun format={formatEffect} />)
    const ramp = container.querySelectorAll('[style*="--chart-scale"]')
    expect(ramp).toHaveLength(SCALE_STEPS)
  })
})
