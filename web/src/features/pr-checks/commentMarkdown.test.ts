import { describe, expect, test } from 'vitest'

import { parseCommentMarkdown, parseSpans } from './commentMarkdown'

const GATE_COMMENT = [
  'Bisect · agent regression detected',
  'scenario suite     reschedule_flight_change (24 tasks x 4 runs)',
  'pass rate          base 0.88  ->  head 0.58   (p = 0.023)',
  'decisive step      step 10',
  'what changed at step 10',
  '  - asks for the reservation ID before looking anything up',
  '  + looks up the most recent reservation by user_id',
  '',
  '48 model calls · details -> bisect serve',
].join('\n')

describe('parseCommentMarkdown', () => {
  test('treats the first line as the comment title', () => {
    // Act
    const blocks = parseCommentMarkdown(GATE_COMMENT)

    // Assert
    expect(blocks[0]).toMatchObject({ kind: 'heading', level: 2 })
  })

  test('reads the gate label/value rows as definitions', () => {
    // Act
    const blocks = parseCommentMarkdown(GATE_COMMENT)

    // Assert
    const definitions = blocks.filter((block) => block.kind === 'definition')
    expect(definitions.map((block) => block.term)).toEqual([
      'scenario suite',
      'pass rate',
      'decisive step',
    ])
  })

  test('reads indented minus and plus lines as a diff', () => {
    // Act
    const diffs = parseCommentMarkdown(GATE_COMMENT).filter((block) => block.kind === 'diff')

    // Assert
    expect(diffs).toHaveLength(2)
    expect(diffs[0]).toMatchObject({ sign: '-' })
    expect(diffs[1]).toMatchObject({ sign: '+' })
  })

  test('drops blank lines rather than emitting empty blocks', () => {
    expect(parseCommentMarkdown(GATE_COMMENT).some((block) => block.kind === 'paragraph')).toBe(
      true,
    )
    expect(parseCommentMarkdown('\n\n\n')).toEqual([])
  })

  test('reads headings at every supported level', () => {
    // Act
    const blocks = parseCommentMarkdown('# one\n## two\n### three')

    // Assert
    expect(blocks.map((block) => (block.kind === 'heading' ? block.level : null))).toEqual([
      1, 2, 3,
    ])
  })

  test('reads bullets', () => {
    expect(parseCommentMarkdown('title\n- first\n- second')).toHaveLength(3)
  })
})

describe('parseSpans', () => {
  test('reads bold and code, and leaves the rest as text', () => {
    // Act
    const spans = parseSpans('pass rate **fell** to `0.58`')

    // Assert
    expect(spans).toEqual([
      { kind: 'text', text: 'pass rate ' },
      { kind: 'strong', text: 'fell' },
      { kind: 'text', text: ' to ' },
      { kind: 'code', text: '0.58' },
    ])
  })

  test('leaves an unmatched marker as literal text', () => {
    expect(parseSpans('a ** b')).toEqual([{ kind: 'text', text: 'a ** b' }])
  })
})

describe('markup in the comment body', () => {
  const HOSTILE = [
    'Bisect · report',
    '<script>alert(1)</script>',
    '<img src=x onerror="alert(2)">',
    'link      <a href="javascript:alert(3)">click</a>',
  ].join('\n')

  test('never produces a raw-HTML block, only text spans', () => {
    // Act
    const blocks = parseCommentMarkdown(HOSTILE)

    // Assert — every block is one of the known kinds; none carries HTML.
    const kinds = new Set(blocks.map((block) => block.kind))
    expect([...kinds].every((kind) => ['heading', 'definition', 'paragraph'].includes(kind))).toBe(
      true,
    )
  })

  test('keeps the tags as literal text, so nothing can execute', () => {
    // Act
    const blocks = parseCommentMarkdown(HOSTILE)
    const texts = blocks.flatMap((block) =>
      'spans' in block ? block.spans.map((span) => `${span.kind}:${span.text}`) : [],
    )

    // Assert
    expect(texts).toContain('text:<script>alert(1)</script>')
    expect(texts.every((entry) => entry.startsWith('text:'))).toBe(true)
  })
})
