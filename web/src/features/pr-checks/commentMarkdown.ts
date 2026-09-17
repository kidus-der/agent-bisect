/**
 * A parser for the small markdown subset the gate's PR comment uses.
 *
 * It produces a block tree, never an HTML string, so the renderer can build
 * React elements and nothing is ever handed to `dangerouslySetInnerHTML`. Any
 * markup in the comment — `<script>`, `<img onerror=...>` — therefore ends up as
 * literal text, which is both safe and the honest rendering of a comment body
 * that came from the server.
 */

export type SpanKind = 'text' | 'strong' | 'code'

export interface Span {
  readonly kind: SpanKind
  readonly text: string
}

export type CommentBlock =
  | { readonly kind: 'heading'; readonly level: 1 | 2 | 3; readonly spans: readonly Span[] }
  | { readonly kind: 'definition'; readonly term: string; readonly spans: readonly Span[] }
  | { readonly kind: 'diff'; readonly sign: '+' | '-'; readonly text: string }
  | { readonly kind: 'bullet'; readonly spans: readonly Span[] }
  | { readonly kind: 'paragraph'; readonly spans: readonly Span[] }

/** `**bold**` and `` `code` ``; everything else stays literal text. */
const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g
const HEADING_PATTERN = /^(#{1,3})\s+(.*)$/
/** A label and a value separated by a run of spaces: the gate's own layout. */
const DEFINITION_PATTERN = /^(\S.*?\S) {2,}(\S.*)$/
/** Indented `-` / `+`: the diff of what changed at the decisive step. */
const DIFF_PATTERN = /^\s+([-+])\s(.*)$/
const BULLET_PATTERN = /^[-*]\s+(.*)$/

const STRONG_MARK_LENGTH = 2
const CODE_MARK_LENGTH = 1

export function parseSpans(line: string): readonly Span[] {
  if (line === '') return []
  return line
    .split(INLINE_PATTERN)
    .filter((piece) => piece !== '')
    .map<Span>((piece) => {
      if (piece.startsWith('**') && piece.endsWith('**') && piece.length > STRONG_MARK_LENGTH * 2) {
        return { kind: 'strong', text: piece.slice(STRONG_MARK_LENGTH, -STRONG_MARK_LENGTH) }
      }
      if (piece.startsWith('`') && piece.endsWith('`') && piece.length > CODE_MARK_LENGTH * 2) {
        return { kind: 'code', text: piece.slice(CODE_MARK_LENGTH, -CODE_MARK_LENGTH) }
      }
      return { kind: 'text', text: piece }
    })
}

function parseLine(line: string, index: number): CommentBlock | null {
  if (line.trim() === '') return null

  const heading = HEADING_PATTERN.exec(line)
  if (heading) {
    const level = Math.min(3, heading[1]?.length ?? 1) as 1 | 2 | 3
    return { kind: 'heading', level, spans: parseSpans(heading[2] ?? '') }
  }

  const diff = DIFF_PATTERN.exec(line)
  if (diff) {
    return { kind: 'diff', sign: diff[1] === '+' ? '+' : '-', text: diff[2] ?? '' }
  }

  const bullet = BULLET_PATTERN.exec(line)
  if (bullet) return { kind: 'bullet', spans: parseSpans(bullet[1] ?? '') }

  // The gate's first line is its own title, whatever it happens to contain.
  if (index === 0) return { kind: 'heading', level: 2, spans: parseSpans(line.trim()) }

  const definition = DEFINITION_PATTERN.exec(line)
  if (definition) {
    return { kind: 'definition', term: definition[1] ?? '', spans: parseSpans(definition[2] ?? '') }
  }

  return { kind: 'paragraph', spans: parseSpans(line.trim()) }
}

export function parseCommentMarkdown(markdown: string): readonly CommentBlock[] {
  return markdown.split('\n').flatMap((line, index) => {
    const block = parseLine(line, index)
    return block ? [block] : []
  })
}
