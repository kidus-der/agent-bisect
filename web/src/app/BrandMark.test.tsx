import { render } from '@testing-library/react'
import { expect, test } from 'vitest'

import { BrandMark } from './BrandMark'

test('the brand mark never spends the blame colours on chrome', () => {
  const { container } = render(<BrandMark />)
  expect(container.innerHTML).not.toMatch(/--bx-blame/)
  expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
})
