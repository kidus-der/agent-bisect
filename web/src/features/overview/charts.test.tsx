import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { CostAccuracyScatter, toScatterPoints } from './CostAccuracyScatter'
import { RecallCurve } from './RecallCurve'
import { accuracyIntervals } from './api'
import type { CostAccuracyPoint, MethodResult, RecallPoint } from './api'

const RECALL: readonly RecallPoint[] = [
  { m: 1, recall: 0.7674 },
  { m: 2, recall: 0.8023 },
  { m: 3, recall: 0.8372 },
  { m: 4, recall: 0.907 },
]

const COST_POINTS: readonly CostAccuracyPoint[] = [
  { method: 'bisect', mean_cost_usd: 1.5607, accuracy: 0.9651 },
  { method: 'judge_all_at_once', mean_cost_usd: 0.03, accuracy: 0.7674 },
]

const METHODS: readonly MethodResult[] = [
  {
    method: 'bisect',
    accuracy: { value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 },
    mean_cost_usd: 1.5607,
    mean_calls: 780.35,
  },
]

describe('RecallCurve', () => {
  test('describes the curve in text, including the pre-registered m', () => {
    render(<RecallCurve points={RECALL} />)
    expect(screen.getByText(/rises from 76\.7% at m=1 to 90\.7% at m=4/)).toBeInTheDocument()
    expect(screen.getByText(/pre-registered m=3 it is 83\.7%/)).toBeInTheDocument()
  })

  test('says so rather than drawing an empty axis when no points were reported', () => {
    render(<RecallCurve points={[]} />)
    expect(screen.getByText('No recall@m points reported.')).toBeInTheDocument()
  })
})

describe('toScatterPoints', () => {
  test('attaches the interval reported for that method', () => {
    const points = toScatterPoints(COST_POINTS, accuracyIntervals(METHODS))
    expect(points[0]?.interval).toEqual({ value: 0.9651, ci_low: 0.9024, ci_high: 0.9881 })
  })

  test('leaves the interval null when none was reported, rather than inventing one', () => {
    const points = toScatterPoints(COST_POINTS, accuracyIntervals(METHODS))
    expect(points[1]?.interval).toBeNull()
  })

  test('yields no intervals at all when the benchmark request failed', () => {
    const points = toScatterPoints(COST_POINTS, accuracyIntervals(null))
    expect(points.every((point) => point.interval === null)).toBe(true)
  })
})

describe('CostAccuracyScatter', () => {
  test('names every method and its cost in the text alternative', () => {
    const points = toScatterPoints(COST_POINTS, accuracyIntervals(METHODS))
    render(<CostAccuracyScatter points={points} intervalsUnavailable={false} />)
    expect(screen.getByText(/Bisect: \$1\.56 per diagnosis at 96\.5%/)).toBeInTheDocument()
    expect(screen.getByText(/95% CI 90\.2% to 98\.8%/)).toBeInTheDocument()
  })

  test('admits when a method carries no interval', () => {
    const points = toScatterPoints(COST_POINTS, accuracyIntervals(METHODS))
    render(<CostAccuracyScatter points={points} intervalsUnavailable={false} />)
    expect(screen.getByText(/\(no interval reported\)/)).toBeInTheDocument()
  })

  test('flags that intervals are unavailable instead of showing bare dots silently', () => {
    const points = toScatterPoints(COST_POINTS, accuracyIntervals(null))
    render(<CostAccuracyScatter points={points} intervalsUnavailable />)
    expect(screen.getByText('intervals unavailable_')).toBeInTheDocument()
  })
})
