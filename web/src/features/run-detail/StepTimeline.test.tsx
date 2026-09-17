import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { StepView } from './api'
import type { HeatCell } from './blame'
import { StepTimeline } from './StepTimeline'

const STEPS: readonly StepView[] = [
  {
    step_idx: 1,
    actor: 'user',
    tool_name: null,
    text: 'asks',
    from_tape: true,
    state_changed: false,
  },
  {
    step_idx: 2,
    actor: 'agent',
    tool_name: null,
    text: 'thinks',
    from_tape: true,
    state_changed: false,
  },
  {
    step_idx: 3,
    actor: 'tool',
    tool_name: 'get_reservation_details',
    text: 'returned',
    from_tape: true,
    state_changed: true,
  },
  {
    step_idx: 4,
    actor: 'agent',
    tool_name: null,
    text: 'answers',
    from_tape: false,
    state_changed: false,
  },
]

const CELLS: readonly HeatCell[] = [
  { step: 1, effect: null, low: null, high: null, tested: false },
  { step: 2, effect: 0.1, low: -0.1, high: 0.3, tested: true },
  { step: 3, effect: 0.88, low: 0.47, high: 0.97, tested: true },
  { step: 4, effect: null, low: null, high: null, tested: false },
]

function Harness({ onChange }: { readonly onChange?: (step: number) => void }) {
  const [playhead, setPlayhead] = useState(1)
  return (
    <StepTimeline
      steps={STEPS}
      states={['ran', 'ran', 'ran', 'pending']}
      cells={CELLS}
      blamedStep={3}
      playhead={playhead}
      onPlayheadChange={(step) => {
        setPlayhead(step)
        onChange?.(step)
      }}
      rewind={null}
      onRewind={() => undefined}
      onResetRewind={() => undefined}
      canRewind
      rerunCount={8}
      intervention={null}
    />
  )
}

describe('StepTimeline playhead', () => {
  it('exposes the step, the total and what happened there as slider value text', () => {
    // Arrange / Act
    render(<Harness />)

    // Assert
    const slider = screen.getByRole('slider', { name: 'Step playhead' })
    expect(slider).toHaveAttribute('aria-valuenow', '1')
    expect(slider).toHaveAttribute('aria-valuemax', '4')
    expect(slider).toHaveAttribute('aria-valuetext', 'step 1 of 4, user')
  })

  it('names the tool at a tool step, as a screen reader needs to hear it', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const slider = screen.getByRole('slider', { name: 'Step playhead' })

    await user.click(slider)
    await user.keyboard('{ArrowRight}{ArrowRight}')

    expect(slider).toHaveAttribute('aria-valuetext', 'step 3 of 4, tool get_reservation_details')
  })

  it('moves one step with the arrows and clamps at both ends', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const slider = screen.getByRole('slider', { name: 'Step playhead' })
    slider.focus()

    await user.keyboard('{ArrowLeft}')
    expect(slider).toHaveAttribute('aria-valuenow', '1')

    await user.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}')
    expect(slider).toHaveAttribute('aria-valuenow', '4')
  })

  it('jumps to the ends with Home and End', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const slider = screen.getByRole('slider', { name: 'Step playhead' })
    slider.focus()

    await user.keyboard('{End}')
    expect(slider).toHaveAttribute('aria-valuenow', '4')
    await user.keyboard('{Home}')
    expect(slider).toHaveAttribute('aria-valuenow', '1')
  })

  it('pages by five, clamped to the tape', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const slider = screen.getByRole('slider', { name: 'Step playhead' })
    slider.focus()

    await user.keyboard('{PageUp}')
    expect(slider).toHaveAttribute('aria-valuenow', '4')
    await user.keyboard('{PageDown}')
    expect(slider).toHaveAttribute('aria-valuenow', '1')
  })

  it('reads out the effect with its interval, and says so when a step is untested', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const slider = screen.getByRole('slider', { name: 'Step playhead' })
    slider.focus()

    expect(screen.getByText('not tested · no effect estimated')).toBeInTheDocument()
    await user.keyboard('{ArrowRight}{ArrowRight}')
    expect(screen.getByText('effect +0.88 [+0.47, +0.97]')).toBeInTheDocument()
  })

  it('does not re-commit the playhead while the pointer stays on the same step', () => {
    // Arrange: jsdom reports a zero rect, so any pointer x resolves to step 1.
    const onPlayheadChange = vi.fn()
    render(
      <StepTimeline
        steps={STEPS}
        states={['ran', 'ran', 'ran', 'pending']}
        cells={CELLS}
        blamedStep={3}
        playhead={1}
        onPlayheadChange={onPlayheadChange}
        rewind={null}
        onRewind={() => undefined}
        onResetRewind={() => undefined}
        canRewind
        rerunCount={8}
        intervention={null}
      />,
    )
    const slider = screen.getByRole('slider', { name: 'Step playhead' })

    // Act: pressing on the step the playhead already occupies.
    fireEvent.pointerDown(slider, { pointerId: 1, clientX: 0 })

    // Assert: a drag must not push identical state on every frame.
    expect(onPlayheadChange).not.toHaveBeenCalled()
  })

  it('commits the playhead when the pointer lands on a different step', () => {
    const onPlayheadChange = vi.fn()
    render(
      <StepTimeline
        steps={STEPS}
        states={['ran', 'ran', 'ran', 'pending']}
        cells={CELLS}
        blamedStep={3}
        playhead={4}
        onPlayheadChange={onPlayheadChange}
        rewind={null}
        onRewind={() => undefined}
        onResetRewind={() => undefined}
        canRewind
        rerunCount={8}
        intervention={null}
      />,
    )

    fireEvent.pointerDown(screen.getByRole('slider', { name: 'Step playhead' }), {
      pointerId: 1,
      clientX: 0,
    })

    expect(onPlayheadChange).toHaveBeenCalledExactlyOnceWith(1)
  })

  it('offers a rewind control that names the step it would rewind to', async () => {
    const onRewind = vi.fn()
    render(
      <StepTimeline
        steps={STEPS}
        states={['ran', 'ran', 'ran', 'pending']}
        cells={CELLS}
        blamedStep={3}
        playhead={3}
        onPlayheadChange={() => undefined}
        rewind={null}
        onRewind={onRewind}
        onResetRewind={() => undefined}
        canRewind
        rerunCount={8}
        intervention={null}
      />,
    )

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Rewind to k=3' }))
    expect(onRewind).toHaveBeenCalledOnce()
  })

  it('disables the rewind control for a step that was never tested', () => {
    render(
      <StepTimeline
        steps={STEPS}
        states={['ran', 'ran', 'ran', 'pending']}
        cells={CELLS}
        blamedStep={3}
        playhead={1}
        onPlayheadChange={() => undefined}
        rewind={null}
        onRewind={() => undefined}
        onResetRewind={() => undefined}
        canRewind={false}
        rerunCount={8}
        intervention={null}
      />,
    )

    expect(screen.getByRole('button', { name: 'Rewind to k=1' })).toBeDisabled()
  })
})
