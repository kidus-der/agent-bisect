import { render } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { PercentYAxis } from './PercentYAxis'

const scale = (value: number): number => 200 - value * 200

function renderAxis(props: Partial<Parameters<typeof PercentYAxis>[0]> = {}) {
  return render(
    <svg>
      <PercentYAxis ticks={[0, 0.5, 1]} scale={scale} width={300} {...props} />
    </svg>,
  )
}

describe('PercentYAxis', () => {
  test('labels proportions as whole percentages', () => {
    const { container } = renderAxis()
    expect([...container.querySelectorAll('text')].map((node) => node.textContent)).toEqual([
      '0',
      '50',
      '100',
    ])
  })

  test('draws one gridline per tick, spanning the plot', () => {
    const { container } = renderAxis()
    const lines = [...container.querySelectorAll('line')]
    expect(lines).toHaveLength(3)
    expect(lines[0]?.getAttribute('x2')).toBe('300')
  })

  test('places each label on its own gridline', () => {
    const { container } = renderAxis()
    const [zero, half, one] = [...container.querySelectorAll('text')]
    expect(zero?.getAttribute('y')).toBe('200')
    expect(half?.getAttribute('y')).toBe('100')
    expect(one?.getAttribute('y')).toBe('0')
  })

  test('handles a truncated axis that does not start at zero', () => {
    const { container } = renderAxis({ ticks: [0.5, 0.75, 1] })
    expect([...container.querySelectorAll('text')].map((node) => node.textContent)).toEqual([
      '50',
      '75',
      '100',
    ])
  })

  test('draws a rotated title only when one is given', () => {
    expect(renderAxis().container.querySelectorAll('text')).toHaveLength(3)
    const titled = renderAxis({ title: 'step accuracy (%)', height: 200 })
    const title = [...titled.container.querySelectorAll('text')].at(-1)
    expect(title?.textContent).toBe('step accuracy (%)')
    expect(title?.getAttribute('transform')).toContain('rotate(-90)')
  })

  test('is hidden from assistive tech, which reads the figure description instead', () => {
    const { container } = renderAxis()
    expect(container.querySelector('g')).toHaveAttribute('aria-hidden', 'true')
  })
})
