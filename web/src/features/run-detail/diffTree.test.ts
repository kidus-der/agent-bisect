import { describe, expect, it } from 'vitest'

import type { DiffEntry } from './api'
import { buildDiffTree, diffCounts } from './diffTree'

const ENTRIES: readonly DiffEntry[] = [
  { path: 'user.membership', kind: 'changed', before: '21MM', after: 'U9JL' },
  { path: 'user.name', kind: 'changed', before: 'A', after: 'B' },
  { path: 'reservations.NM1VX1', kind: 'removed', before: '{...}', after: null },
  { path: 'reservations.ZFA04Y', kind: 'added', before: null, after: '{...}' },
]

describe('diffCounts', () => {
  it('counts each kind of change', () => {
    expect(diffCounts(ENTRIES)).toEqual({ added: 1, removed: 1, changed: 2 })
  })

  it('counts nothing for an empty diff', () => {
    expect(diffCounts([])).toEqual({ added: 0, removed: 0, changed: 0 })
  })
})

describe('buildDiffTree', () => {
  it('groups paths under their common parent', () => {
    // Act
    const tree = buildDiffTree(ENTRIES)

    // Assert
    expect(tree.map((node) => node.name)).toEqual(['reservations', 'user'])
    expect(tree[0]?.children.map((child) => child.name)).toEqual(['NM1VX1', 'ZFA04Y'])
  })

  it('carries the entry on the leaf and nothing on a branch', () => {
    const tree = buildDiffTree(ENTRIES)
    const user = tree[1]

    expect(user?.entry).toBeNull()
    expect(user?.children[0]?.entry).toEqual(ENTRIES[0])
  })

  it('rolls the counts up to every ancestor', () => {
    const tree = buildDiffTree(ENTRIES)

    expect(tree[0]?.counts).toEqual({ added: 1, removed: 1, changed: 0 })
    expect(tree[1]?.counts).toEqual({ added: 0, removed: 0, changed: 2 })
  })

  it('keeps the full path on every node so keys stay unique', () => {
    const tree = buildDiffTree(ENTRIES)

    expect(tree[1]?.path).toBe('user')
    expect(tree[1]?.children[0]?.path).toBe('user.membership')
  })

  it('handles a single-segment path as its own leaf', () => {
    const tree = buildDiffTree([{ path: 'seed', kind: 'changed', before: '1', after: '2' }])

    expect(tree).toHaveLength(1)
    expect(tree[0]?.children).toHaveLength(0)
    expect(tree[0]?.entry?.path).toBe('seed')
  })

  it('returns nothing for an empty diff', () => {
    expect(buildDiffTree([])).toEqual([])
  })
})
