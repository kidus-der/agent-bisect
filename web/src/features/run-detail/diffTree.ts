/**
 * The DB-state diff between `state_before` and `state_after`, grouped by path so
 * a 40-key diff reads as a tree instead of a flat wall of dotted paths.
 */
import type { DiffEntry } from './api'

export type DiffKind = DiffEntry['kind']

export interface DiffCounts {
  readonly added: number
  readonly removed: number
  readonly changed: number
}

export interface DiffNode {
  /** Last path segment: what this node is called under its parent. */
  readonly name: string
  /** Full dotted path, unique within the tree. */
  readonly path: string
  readonly children: readonly DiffNode[]
  /** The change itself, on leaves only. */
  readonly entry: DiffEntry | null
  readonly counts: DiffCounts
}

const EMPTY_COUNTS: DiffCounts = { added: 0, removed: 0, changed: 0 }

export function diffCounts(entries: readonly DiffEntry[]): DiffCounts {
  return entries.reduce<DiffCounts>(
    (totals, entry) => ({ ...totals, [entry.kind]: totals[entry.kind] + 1 }),
    EMPTY_COUNTS,
  )
}

interface Draft {
  readonly name: string
  readonly path: string
  readonly children: Map<string, Draft>
  entry: DiffEntry | null
}

function child(parent: Map<string, Draft>, name: string, path: string): Draft {
  const existing = parent.get(name)
  if (existing) return existing
  const created: Draft = { name, path, children: new Map(), entry: null }
  parent.set(name, created)
  return created
}

function freeze(draft: Draft): DiffNode {
  const children = [...draft.children.values()]
    .map(freeze)
    .sort((a, b) => a.name.localeCompare(b.name))
  const own = draft.entry ? { ...EMPTY_COUNTS, [draft.entry.kind]: 1 } : EMPTY_COUNTS
  const counts = children.reduce<DiffCounts>(
    (totals, node) => ({
      added: totals.added + node.counts.added,
      removed: totals.removed + node.counts.removed,
      changed: totals.changed + node.counts.changed,
    }),
    own,
  )
  return { name: draft.name, path: draft.path, children, entry: draft.entry, counts }
}

/** Dotted paths -> a tree whose branches carry the rolled-up counts. */
export function buildDiffTree(entries: readonly DiffEntry[]): readonly DiffNode[] {
  const roots = new Map<string, Draft>()
  for (const entry of entries) {
    const segments = entry.path.split('.')
    let level = roots
    let node: Draft | null = null
    let prefix = ''
    for (const segment of segments) {
      prefix = prefix ? `${prefix}.${segment}` : segment
      node = child(level, segment, prefix)
      level = node.children
    }
    if (node) node.entry = entry
  }
  return [...roots.values()].map(freeze).sort((a, b) => a.name.localeCompare(b.name))
}
