/**
 * The Runs row is the "from" half of the list -> detail morph (signature moment
 * §7.4), and the Run detail header is the "to" half. They pair on three exact
 * ids, so a rename on either side silently turns the morph into a cut with
 * nothing failing — these tests are what makes that fail loudly.
 *
 * Motion does not put `layoutId` in the DOM, so `motion.*` is replaced here with
 * plain elements that expose it as `data-layout-id`. The cells are rendered
 * directly rather than through the table: the row is virtualized, and jsdom has
 * no layout engine, so a real table renders an empty body here.
 */
import { render, screen } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, test, vi } from 'vitest'

import type { RunSummary } from './api'
import { RunBlameStripeCell, RunIdChip, RunOutcomeCell } from './RunsTable'

/**
 * Motion reads the reduced-motion query once, when it is imported, so stubbing
 * `matchMedia` inside a test comes too late to change it.
 */
const motionState = vi.hoisted(() => ({ reduced: false }))

/** Props motion consumes itself; React would warn about them on a DOM element. */
const MOTION_PROPS: readonly string[] = [
  'transition',
  'initial',
  'animate',
  'exit',
  'whileHover',
  'whileTap',
  'layout',
  'layoutId',
  'variants',
]

vi.mock('motion/react', async (importActual) => {
  const actual = await importActual<typeof import('motion/react')>()
  const mock = (tag: string) =>
    function MockMotion({ children, ...props }: { children?: ReactNode }) {
      const passed = props as Record<string, unknown>
      const plain = Object.fromEntries(
        Object.entries(passed).filter(([key]) => !MOTION_PROPS.includes(key)),
      )
      const layoutId = passed.layoutId
      return createElement(
        tag,
        { ...plain, ...(typeof layoutId === 'string' ? { 'data-layout-id': layoutId } : {}) },
        children,
      )
    }
  return {
    ...actual,
    useReducedMotion: () => motionState.reduced,
    motion: new Proxy({} as Record<string, unknown>, { get: (_target, tag: string) => mock(tag) }),
  }
})

const RUN: RunSummary = {
  run_id: 'brief-12-step',
  domain: 'airline',
  task_id: 'refund_after_cancellation',
  model: 'nvidia/llama-3.1-nemotron-70b-instruct',
  status: 'complete',
  outcome: 'fail',
  n_steps: 12,
  decisive_step: 7,
  fault_type: 'wrong_value',
  planted_step: 7,
  cost_usd: 0.97,
  calls: 470,
  sparkline: [],
  blame_stripe: [
    { step_idx: 1, effect: 0.1, tested: true },
    { step_idx: 7, effect: 0.88, tested: true },
  ],
}

function renderRowCells(): void {
  render(
    <>
      <RunIdChip runId={RUN.run_id} />
      <RunBlameStripeCell run={RUN} />
      <RunOutcomeCell run={RUN} />
    </>,
  )
}

function layoutIdsInDom(): readonly string[] {
  return [...document.querySelectorAll('[data-layout-id]')].map(
    (element) => element.getAttribute('data-layout-id') ?? '',
  )
}

describe('the morph targets the Run detail header pairs with', () => {
  test('the row carries the id chip, blame stripe and status ids', () => {
    motionState.reduced = false

    renderRowCells()

    expect(layoutIdsInDom()).toEqual([
      'run-brief-12-step-id',
      'run-brief-12-step-blame-stripe',
      'run-brief-12-step-status',
    ])
  })

  test('reduced motion carries no layout id at all, so the pages swap instantly', () => {
    motionState.reduced = true

    renderRowCells()

    expect(layoutIdsInDom()).toEqual([])
    // The content is still there — it is only the travelling that is dropped.
    expect(screen.getByText('brief-12-step')).toBeInTheDocument()
  })
})
