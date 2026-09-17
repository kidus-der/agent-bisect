import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { ActorGlyph } from './ActorGlyph'
import { BlameBadge } from './BlameBadge'
import { EffectWithCI } from './EffectWithCI'
import { HeatStripe } from './HeatStripe'
import { InstrumentLabel } from './InstrumentLabel'
import { Kbd } from './Kbd'
import { PassFailPill } from './PassFailPill'
import { StepSparkline } from './StepSparkline'
import { TapeStep } from './TapeStep'

describe('PassFailPill', () => {
  test('never conveys the outcome by colour alone: glyph and word are both rendered', () => {
    const { container } = render(<PassFailPill outcome="fail" />)
    expect(screen.getByText('Fail')).toBeInTheDocument()
    expect(container.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
    expect(container.firstElementChild).toHaveAttribute('data-outcome', 'fail')
  })

  test('accepts a custom label such as a pass count', () => {
    render(<PassFailPill outcome="pass" label="7/8 pass" />)
    expect(screen.getByText('7/8 pass')).toBeInTheDocument()
  })
})

describe('BlameBadge', () => {
  test('always shows the effect number next to the blamed step', () => {
    render(<BlameBadge step={7} effect={0.75} />)
    expect(screen.getByText('+0.75')).toBeInTheDocument()
    expect(screen.getByText(/step 7/)).toBeInTheDocument()
  })

  test('renders the interval when one is given, and reads as a sentence to a screen reader', () => {
    const { container } = render(<BlameBadge step={7} effect={0.75} interval={[0.41, 0.94]} />)
    expect(screen.getByText('[+0.41, +0.94]')).toBeInTheDocument()
    expect(container.textContent).toBe(
      'Blame: step 7effect +0.7595% confidence interval [+0.41, +0.94]',
    )
  })

  test('puts the number on a solid amber chip, not on the gradient', () => {
    render(<BlameBadge step={7} effect={0.75} />)
    const chip = screen.getByText('+0.75').closest('span.bg-blame')
    expect(chip).not.toBeNull()
    expect(chip).not.toHaveClass('blame-gradient')
  })
})

describe('EffectWithCI', () => {
  test('an estimate never appears without its interval', () => {
    render(<EffectWithCI estimate={0.38} low={0.07} high={0.66} />)
    expect(screen.getByText('+0.38')).toBeInTheDocument()
    expect(screen.getByText('[+0.07, +0.66]')).toBeInTheDocument()
  })

  test('the bar-only variant keeps the numbers for assistive tech', () => {
    const { container } = render(
      <EffectWithCI estimate={0.38} low={0.07} high={0.66} variant="bar" />,
    )
    expect(container.querySelector('svg')).not.toBeNull()
    expect(screen.getByText('[+0.07, +0.66]').closest('.sr-only')).not.toBeNull()
  })

  test('the text variant draws no bar, and δ is a dashed line when drawn', () => {
    const text = render(<EffectWithCI estimate={0.1} low={0} high={0.2} variant="text" />)
    expect(text.container.querySelector('svg')).toBeNull()
    const bar = render(<EffectWithCI estimate={0.1} low={0} high={0.2} delta={0.2} />)
    expect(bar.container.querySelector('line[stroke-dasharray]')).not.toBeNull()
  })
})

describe('HeatStripe', () => {
  const steps = [
    { step: 1, effect: null },
    { step: 2, effect: 0.2 },
    { step: 3, effect: 0.75 },
    { step: 4, effect: null },
  ]

  test('untested steps are hatched with an SVG pattern, never a scale colour', () => {
    const { container } = render(<HeatStripe steps={steps} blamedStep={3} />)
    const untested = container.querySelectorAll('rect[data-state="untested"]')
    expect(untested).toHaveLength(2)
    untested.forEach((cell) => expect(cell.getAttribute('fill')).toMatch(/^url\(#.*hatch\)$/))
    expect(container.querySelector('pattern')).not.toBeNull()
  })

  test('tested steps use the sequential scale and the blamed step uses the blame gradient', () => {
    const { container } = render(<HeatStripe steps={steps} blamedStep={3} />)
    // One tested non-blamed step is no spread, so it takes the middle bucket
    // rather than implying a gradient that was never measured.
    expect(container.querySelector('rect[data-state="tested"]')?.getAttribute('fill')).toBe(
      'var(--chart-scale-03)',
    )
    expect(container.querySelector('rect[data-state="blamed"]')?.getAttribute('fill')).toMatch(
      /blame\)$/,
    )
  })

  test('spreads ordinary steps across the ramp instead of flattening them under the blamed one', () => {
    const spread = [
      { step: 1, effect: -0.06 },
      { step: 2, effect: 0.06 },
      { step: 3, effect: 0.25 },
      { step: 4, effect: 0.88 },
    ]
    const { container } = render(<HeatStripe steps={spread} blamedStep={4} />)
    const fills = [...container.querySelectorAll('rect[data-state="tested"]')].map((cell) =>
      cell.getAttribute('fill'),
    )
    expect(new Set(fills).size).toBe(3)
  })

  test('a fixed track divides by the step count, so stripes share one length', () => {
    const short = render(<HeatStripe steps={steps} trackWidth={120} />)
    const long = render(
      <HeatStripe
        steps={Array.from({ length: 27 }, (_, index) => ({ step: index + 1, effect: 0.1 }))}
        trackWidth={120}
      />,
    )
    expect(short.container.querySelector('svg')?.getAttribute('width')).toBe('120')
    expect(long.container.querySelector('svg')?.getAttribute('width')).toBe('120')
  })

  test('has an accessible description and shows the blame number', () => {
    render(<HeatStripe steps={steps} blamedStep={3} />)
    expect(
      screen.getByRole('img', {
        name: 'Effect per step: 4 steps, 2 tested, 2 untested (hatched). Largest effect +0.75 at step 3. Blamed step: 3.',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('#3 +0.75')).toBeInTheDocument()
  })

  test('a blamed step that was never tested is still hatched', () => {
    const { container } = render(<HeatStripe steps={steps} blamedStep={1} />)
    expect(container.querySelector('rect[data-state="blamed"]')).toBeNull()
  })
})

describe('StepSparkline', () => {
  test('describes the series and marks the requested step', () => {
    const { container } = render(
      <StepSparkline values={[3, 9, 4]} label="tokens per step" markIndex={1} />,
    )
    expect(
      screen.getByRole('img', { name: 'tokens per step: 3 steps, min 3, max 9, step 2 marked' }),
    ).toBeInTheDocument()
    expect(container.querySelectorAll('circle')).toHaveLength(1)
  })

  test('renders text instead of an empty chart when there are no steps', () => {
    render(<StepSparkline values={[]} label="tokens per step" />)
    expect(screen.getByText('no steps')).toBeInTheDocument()
  })
})

describe('ActorGlyph, Kbd, InstrumentLabel', () => {
  test('the actor is named for assistive tech when no visible label is shown', () => {
    render(<ActorGlyph actor="tool" />)
    expect(screen.getByRole('img', { name: 'Tool' })).toBeInTheDocument()
  })

  test('with a visible label the glyph is decorative', () => {
    render(<ActorGlyph actor="agent" showLabel />)
    expect(screen.getByText('Agent')).toBeInTheDocument()
    expect(screen.queryByRole('img')).toBeNull()
  })

  test('Kbd renders a <kbd> and the instrument label appends a decorative underscore', () => {
    render(
      <>
        <Kbd>K</Kbd>
        <InstrumentLabel>recall@m</InstrumentLabel>
      </>,
    )
    expect(screen.getByText('K').tagName).toBe('KBD')
    expect(screen.getByText('_')).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('TapeStep', () => {
  test.each([
    ['live', 'Step 3, agent, running live'],
    ['tape', 'Step 3, agent, read from tape'],
    ['blamed', 'Step 3, agent, blamed'],
    ['failed', 'Step 3, agent, failed'],
    ['passed', 'Step 3, agent, passed'],
  ] as const)('state %s is named "%s"', (state, name) => {
    render(<TapeStep step={3} state={state} actor="agent" />)
    expect(screen.getByRole('img', { name })).toHaveAttribute('data-state', state)
  })

  test('only the blamed state gets the gradient ring and the glow', () => {
    const { rerender } = render(<TapeStep step={1} state="blamed" />)
    expect(screen.getByRole('img')).toHaveClass('blame-gradient', 'shadow-glow-blame')
    rerender(<TapeStep step={1} state="passed" />)
    expect(screen.getByRole('img')).not.toHaveClass('blame-gradient')
  })

  test('becomes a toggle button when selectable', async () => {
    const onSelect = vi.fn()
    render(<TapeStep step={5} state="ran" onSelect={onSelect} selected />)
    const button = screen.getByRole('button', { name: 'Step 5, ran live' })
    expect(button).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(button)
    expect(onSelect).toHaveBeenCalledWith(5)
  })
})
