import { readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, test } from 'vitest'

/**
 * The one rule direction.md calls absolute: amber/coral means blame and nothing
 * else (§3, principle 2). It had already been broken twice — a log level and a
 * connection dot — so it is enforced here rather than left to review.
 *
 * A file may use a `blame` token only if it is on the allow-list below, and the
 * allow-list is itself checked, so an entry that stops using blame has to be
 * removed rather than quietly protecting a future misuse.
 */
// vitest runs from `web/`; `import.meta.url` is not a file URL under jsdom.
const FEATURES_DIR = join(process.cwd(), 'src', 'features')

/** Every Tailwind utility that can paint with the blame role. */
const BLAME_CLASS =
  /\b(?:bg|text|border|from|via|to|ring|fill|stroke|shadow|decoration|outline|accent|caret)-blame(?:-coral)?(?:-tint)?\b|\bblame-gradient\b|\bshadow-glow-blame\b/

/** Files whose blame usage really is blame. Paths relative to `src/features`. */
const ALLOWED = [
  // The head ref's decisive step is the blamed step.
  'pr-checks/DecisiveStepChange.tsx',
] as const

/** Only the three features this guard owns; the rest have their own reviewers. */
const GUARDED = ['benchmark', 'live', 'pr-checks'] as const

function sourceFiles(dir: string): readonly string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    if (!/\.(ts|tsx)$/.test(entry.name) || entry.name.endsWith('.test.tsx')) return []
    if (entry.name.endsWith('.test.ts')) return []
    return [full]
  })
}

function filesUsingBlame(): readonly string[] {
  return GUARDED.flatMap((feature) => sourceFiles(join(FEATURES_DIR, feature)))
    .filter((file) => BLAME_CLASS.test(readFileSync(file, 'utf8')))
    .map((file) => relative(FEATURES_DIR, file))
    .sort()
}

describe('blame colour role', () => {
  test('no file paints with blame outside the allow-list', () => {
    // Act
    const offenders = filesUsingBlame().filter(
      (file) => !(ALLOWED as readonly string[]).includes(file),
    )

    // Assert — amber means blame. A new use must be justified and allow-listed.
    expect(offenders).toEqual([])
  })

  test('every allow-listed file still uses blame, so the list cannot rot', () => {
    // Act
    const using = filesUsingBlame()

    // Assert
    for (const allowed of ALLOWED) {
      expect(using).toContain(allowed)
    }
  })

  test('the pattern it enforces actually matches the utilities in use', () => {
    // A guard that matches nothing would pass silently forever.
    expect(BLAME_CLASS.test('text-blame')).toBe(true)
    expect(BLAME_CLASS.test('bg-blame-tint')).toBe(true)
    expect(BLAME_CLASS.test('border-blame/40')).toBe(true)
    expect(BLAME_CLASS.test('bg-blame-coral')).toBe(true)
    expect(BLAME_CLASS.test('blame-gradient')).toBe(true)
    expect(BLAME_CLASS.test('shadow-glow-blame')).toBe(true)
  })

  test('the pattern does not fire on prose about blame', () => {
    expect(BLAME_CLASS.test('Where the blame rule lands')).toBe(false)
    expect(BLAME_CLASS.test('buildBlameFlow')).toBe(false)
    expect(BLAME_CLASS.test('bisect blame RUN_ID')).toBe(false)
    expect(BLAME_CLASS.test('const blamed = true')).toBe(false)
  })
})
