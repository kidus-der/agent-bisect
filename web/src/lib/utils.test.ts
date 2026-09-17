import { describe, expect, test } from 'vitest'

import { cn } from './utils'

describe('cn', () => {
  test('keeps a design-system font size beside a text colour', () => {
    // Arrange / Act — `text-small` is a font size from typeScale, not a colour.
    const classes = cn('num text-small text-ink')

    // Assert — without teaching tailwind-merge the scale, `text-small` is read as
    // a colour and silently dropped in favour of `text-ink`.
    expect(classes).toContain('text-small')
    expect(classes).toContain('text-ink')
  })

  test.each(['display', 'h1', 'h2', 'h3', 'body', 'small', 'micro', 'stat'])(
    'keeps text-%s beside a text colour',
    (size) => {
      expect(cn(`text-${size} text-ink-muted`)).toContain(`text-${size}`)
    },
  )

  test('still lets one design-system size replace another', () => {
    // Arrange / Act
    const classes = cn('text-small', 'text-h2')

    // Assert
    expect(classes).toBe('text-h2')
  })

  test('still resolves conflicting text colours to the last one', () => {
    expect(cn('text-ink text-ink-muted')).toBe('text-ink-muted')
  })

  test('still merges ordinary conflicting utilities', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })

  test('drops falsy values', () => {
    expect(cn('px-2', false, undefined, null, 'py-1')).toBe('px-2 py-1')
  })
})
