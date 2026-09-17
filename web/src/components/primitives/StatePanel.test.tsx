import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { ErrorState } from './ErrorState'
import { StatePanel } from './StatePanel'

describe('StatePanel', () => {
  test('caps a page-level state at 560px and centres it, instead of stretching across the grid', () => {
    const { container } = render(
      <StatePanel>
        <ErrorState message="Cannot reach the server." />
      </StatePanel>,
    )
    expect(container.firstElementChild).toHaveClass('mx-auto', 'w-full', 'max-w-[560px]')
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  test('keeps the panel variant it is given', () => {
    const { container } = render(<StatePanel variant="canvas">x</StatePanel>)
    expect(container.firstElementChild).toHaveAttribute('data-variant', 'canvas')
  })
})
