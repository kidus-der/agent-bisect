import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import type { RunSummary, SparkPoint } from './api'
import {
  RunBlame,
  RunNumber,
  RunOutcome,
  RunSparkline,
  decisiveEffect,
  sparkSeries,
  stripeCellWidth,
} from './cells'

function run(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_id: 'brief-12-step',
    domain: 'airline',
    task_id: 'refund_after_cancellation',
    model: 'nvidia/llama-3.1-nemotron-70b-instruct',
    status: 'complete',
    outcome: 'fail',
    n_steps: 2,
    decisive_step: 2,
    fault_type: 'wrong_value',
    planted_step: 2,
    cost_usd: 0.97,
    calls: 470,
    sparkline: [],
    blame_stripe: [
      { step_idx: 1, effect: 0.1, tested: true },
      { step_idx: 2, effect: 0.875, tested: true },
    ],
    ...overrides,
  }
}

const POINTS: readonly SparkPoint[] = [
  { step_idx: 1, actor: 'user', latency_ms: 3013, tokens: 102 },
  { step_idx: 2, actor: 'tool', latency_ms: 3169, tokens: 516 },
]

describe('sparkSeries', () => {
  test('prefers tokens per step', () => {
    expect(sparkSeries(POINTS)).toEqual({ values: [102, 516], label: 'tokens per step' })
  })

  test('falls back to latency when tokens were not recorded', () => {
    const points = POINTS.map((point) => ({ ...point, tokens: null }))
    expect(sparkSeries(points)?.label).toBe('latency per step, ms')
  })

  test('draws nothing rather than inventing a zero for a gap', () => {
    const points = [POINTS[0]!, { ...POINTS[1]!, tokens: null, latency_ms: null }]
    expect(sparkSeries(points)).toBeNull()
    expect(sparkSeries([])).toBeNull()
  })
})

describe('stripeCellWidth', () => {
  test('keeps a long stripe the same overall width as a short one', () => {
    expect(stripeCellWidth(12) * 12).toBeLessThanOrEqual(150)
    expect(stripeCellWidth(60) * 60).toBeLessThanOrEqual(150)
    expect(stripeCellWidth(60)).toBeGreaterThanOrEqual(2)
  })
})

describe('decisiveEffect', () => {
  test('reads the effect measured at the decisive step', () => {
    expect(decisiveEffect(run({}))).toBe(0.875)
  })

  test('is null when the decisive step was never tested', () => {
    const untested = run({ blame_stripe: [{ step_idx: 2, effect: null, tested: false }] })
    expect(decisiveEffect(untested)).toBeNull()
    expect(decisiveEffect(run({ decisive_step: null }))).toBeNull()
  })
})

describe('null rendering', () => {
  test('a null cost renders as an em dash, never as zero', () => {
    render(<RunNumber value={null} decimals={2} prefix="$" />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('not measured')).toHaveClass('sr-only')
  })

  test('a real cost renders as a number', () => {
    render(<RunNumber value={0.97} decimals={2} prefix="$" />)
    expect(screen.getByText('$0.97')).toBeInTheDocument()
  })

  test('a run with no sparkline data shows the dash', () => {
    render(<RunSparkline run={run({ sparkline: [] })} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  test('blame with no measured effect shows the dash, not a bare step number', () => {
    render(<RunBlame run={run({ blame_stripe: [{ step_idx: 2, effect: null, tested: false }] })} />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText(/step 2/i)).toBeNull()
  })

  test('blame with an effect shows both the step and the number', () => {
    render(<RunBlame run={run({})} />)
    expect(screen.getByText(/step 2/)).toBeInTheDocument()
    expect(screen.getByText('+0.88')).toBeInTheDocument()
  })
})

describe('RunOutcome', () => {
  test('shows a recording run as recording, never as a failure', () => {
    render(<RunOutcome run={run({ status: 'recording', outcome: null })} />)
    expect(screen.getByText('Recording')).toBeInTheDocument()
    expect(screen.queryByText('Fail')).toBeNull()
  })

  test('shows a completed run with its glyph and word', () => {
    render(<RunOutcome run={run({ status: 'complete', outcome: 'pass' })} />)
    expect(screen.getByText('Pass')).toBeInTheDocument()
  })
})
