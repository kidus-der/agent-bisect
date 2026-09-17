import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { CommentPreview } from './CommentPreview'

const GATE_COMMENT = [
  'Bisect · agent regression detected',
  'scenario suite     reschedule_flight_change (24 tasks x 4 runs)',
  'pass rate          base 0.88  ->  head 0.58   (p = 0.023)',
  'what changed at step 10',
  '  - asks for the reservation ID before looking anything up',
  '  + looks up the most recent reservation by user_id',
].join('\n')

describe('CommentPreview', () => {
  test('renders the gate comment as a GitHub-style comment', () => {
    // Act
    render(<CommentPreview markdown={GATE_COMMENT} prNumber={1000} />)

    // Assert
    expect(screen.getByText('bisect-bot')).toBeInTheDocument()
    expect(screen.getByText('#1000')).toBeInTheDocument()
    expect(screen.getByText('Bisect · agent regression detected')).toBeInTheDocument()
  })

  test('renders the label/value rows as terms and values', () => {
    render(<CommentPreview markdown={GATE_COMMENT} prNumber={1000} />)
    expect(screen.getByText('scenario suite')).toBeInTheDocument()
    expect(screen.getByText('reschedule_flight_change (24 tasks x 4 runs)')).toBeInTheDocument()
  })

  test('labels diff lines for a screen reader, not only by colour', () => {
    render(<CommentPreview markdown={GATE_COMMENT} prNumber={1000} />)
    expect(screen.getByText('removed:')).toBeInTheDocument()
    expect(screen.getByText('added:')).toBeInTheDocument()
  })

  test('offers a copy-markdown action', () => {
    render(<CommentPreview markdown={GATE_COMMENT} prNumber={1000} />)
    expect(screen.getByRole('button', { name: /copy markdown/i })).toBeInTheDocument()
  })
})

describe('CommentPreview safety', () => {
  const HOSTILE = [
    'Bisect · report',
    '<script>alert(1)</script>',
    '<img src=x onerror="alert(2)">',
    'link      <a href="javascript:alert(3)">click</a>',
  ].join('\n')

  test('renders markup in the body as inert text', () => {
    // Act
    const { container } = render(<CommentPreview markdown={HOSTILE} prNumber={7} />)

    // Assert — the tags are visible as text, so they were never parsed as HTML.
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
    expect(screen.getByText('<img src=x onerror="alert(2)">')).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
  })

  test('creates no anchor, so a javascript: url cannot be clicked', () => {
    // Act
    const { container } = render(<CommentPreview markdown={HOSTILE} prNumber={7} />)

    // Assert
    expect(container.querySelector('a')).toBeNull()
    expect(screen.getByText('<a href="javascript:alert(3)">click</a>')).toBeInTheDocument()
  })

  test('escapes the markup rather than letting it reach an attribute', () => {
    // Act
    const { container } = render(<CommentPreview markdown={HOSTILE} prNumber={7} />)

    // Assert — the angle brackets are escaped, so the payload is a text node and
    // no element in the tree carries an attribute that came from it.
    expect(container.innerHTML).toContain('&lt;img src=x onerror="alert(2)"&gt;')
    expect(container.querySelector('[onerror]')).toBeNull()
    expect(container.querySelector('[href]')).toBeNull()
  })
})
