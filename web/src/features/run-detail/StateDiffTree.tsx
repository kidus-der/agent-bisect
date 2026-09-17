import { ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { DiffEntry } from './api'
import {
  type DiffCounts,
  type DiffNode,
  type DiffKind,
  buildDiffTree,
  diffCounts,
} from './diffTree'

const KIND_GLYPH: Readonly<Record<DiffKind, string>> = { added: '+', removed: '−', changed: '~' }
const KIND_STYLE: Readonly<Record<DiffKind, string>> = {
  added: 'border-measure bg-measure-tint',
  removed: 'border-tape bg-tape-tint',
  changed: 'border-line-strong bg-elevated',
}

function CountChip({ kind, value }: { readonly kind: DiffKind; readonly value: number }) {
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center gap-1 rounded-pill border px-1.5 num text-[11px]',
        value === 0 ? 'border-line text-ink-muted opacity-60' : KIND_STYLE[kind],
      )}
    >
      <span aria-hidden="true">{KIND_GLYPH[kind]}</span>
      {value} {kind}
    </span>
  )
}

function Value({ label, text }: { readonly label: string; readonly text: string | null }) {
  return (
    <span className="flex min-w-0 gap-2">
      <span className="shrink-0 text-ink-muted">{label}</span>
      <span className={cn('min-w-0 break-all', text === null ? 'text-ink-muted italic' : '')}>
        {text ?? 'absent'}
      </span>
    </span>
  )
}

function Leaf({ node, entry }: { readonly node: DiffNode; readonly entry: DiffEntry }) {
  return (
    <div className={cn('rounded-step border-l-2 py-1 pr-2 pl-2', KIND_STYLE[entry.kind])}>
      <p className="flex items-baseline gap-2 font-mono text-small">
        <span aria-hidden="true" className="w-2 shrink-0 text-ink-muted">
          {KIND_GLYPH[entry.kind]}
        </span>
        <span className="min-w-0 break-all text-ink">{node.name}</span>
        <span className="sr-only">{entry.kind}</span>
      </p>
      <div className="mt-0.5 flex flex-col gap-0.5 pl-4 font-mono text-small">
        {entry.kind !== 'added' ? <Value label="was" text={entry.before} /> : null}
        {entry.kind !== 'removed' ? <Value label="now" text={entry.after} /> : null}
      </div>
    </div>
  )
}

function Branch({ node, depth }: { readonly node: DiffNode; readonly depth: number }) {
  if (node.entry) return <Leaf node={node} entry={node.entry} />
  return (
    <details open={depth === 0} className="group">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-step py-1 font-mono text-small text-ink hover:bg-elevated">
        <ChevronRight
          aria-hidden="true"
          className="size-3.5 shrink-0 text-ink-muted transition-transform group-open:rotate-90"
        />
        <span className="min-w-0 break-all">{node.name}</span>
        <span className="num text-[11px] text-ink-muted">
          {node.counts.added + node.counts.removed + node.counts.changed}
        </span>
      </summary>
      <div className="flex flex-col gap-1 border-l border-line pt-1 pl-3">
        {node.children.map((childNode) => (
          <Branch key={childNode.path} node={childNode} depth={depth + 1} />
        ))}
      </div>
    </details>
  )
}

interface StateDiffTreeProps {
  readonly entries: readonly DiffEntry[]
  readonly stepIdx: number
}

function summarise(counts: DiffCounts, stepIdx: number): string {
  return `Database state around step ${stepIdx}: ${counts.added} added, ${counts.removed} removed, ${counts.changed} changed.`
}

/** What step k did to the world: state_before vs state_after, as a collapsible tree. */
export function StateDiffTree({ entries, stepIdx }: StateDiffTreeProps) {
  const counts = diffCounts(entries)
  const tree = buildDiffTree(entries)

  if (entries.length === 0) {
    return (
      <p className="py-2 text-small text-ink-muted">
        Step {stepIdx} changed no database state. Nothing was written between{' '}
        <code className="font-mono">state_before</code> and{' '}
        <code className="font-mono">state_after</code>.
      </p>
    )
  }

  return (
    <div>
      <p className="sr-only">{summarise(counts, stepIdx)}</p>
      <div aria-hidden="true" className="mb-3 flex flex-wrap gap-1.5">
        <CountChip kind="added" value={counts.added} />
        <CountChip kind="removed" value={counts.removed} />
        <CountChip kind="changed" value={counts.changed} />
      </div>
      <div className="flex flex-col gap-1">
        {tree.map((node) => (
          <Branch key={node.path} node={node} depth={0} />
        ))}
      </div>
    </div>
  )
}
