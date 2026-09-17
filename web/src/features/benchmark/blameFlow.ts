/**
 * Turns `/api/benchmark`'s flat `sankey` rows into the node/link graph the
 * vendored Sankey chart wants, plus the sentence a screen reader gets instead.
 */
import type { RoleName } from '@/design/tokens'

import type { BlameLabel, FaultType, SankeyFlow } from './api'
import {
  BLAME_LABELS,
  BLAME_LABELS_SHORT,
  BLAME_LABEL_ORDER,
  BLAME_LABEL_ROLES,
  FAULT_TYPE_LABELS,
  FAULT_TYPE_SHORT,
} from './methods'

export type FlowCategory = 'source' | 'outcome'

export interface FlowNode {
  readonly name: string
  readonly category: FlowCategory
  readonly role: RoleName
}

export interface FlowLink {
  readonly source: number
  readonly target: number
  readonly value: number
}

export interface BlameFlowGraph {
  readonly nodes: readonly FlowNode[]
  readonly links: readonly FlowLink[]
  readonly total: number
}

const FAULT_ROLE: RoleName = 'tape'

/** `compact` swaps in the short labels; the text alternative always uses the full ones. */
export function buildBlameFlow(rows: readonly SankeyFlow[], compact = false): BlameFlowGraph {
  const faultName = compact ? FAULT_TYPE_SHORT : FAULT_TYPE_LABELS
  const labelName = compact ? BLAME_LABELS_SHORT : BLAME_LABELS
  const faults = [...new Set(rows.map((row) => row.fault_type))].sort((a, b) =>
    FAULT_TYPE_LABELS[a].localeCompare(FAULT_TYPE_LABELS[b]),
  )
  const labels = BLAME_LABEL_ORDER.filter((label) =>
    rows.some((row) => row.label === label && row.count > 0),
  )

  const faultNodes: readonly FlowNode[] = faults.map((fault) => ({
    name: faultName[fault],
    category: 'source',
    role: FAULT_ROLE,
  }))
  const labelNodes: readonly FlowNode[] = labels.map((label) => ({
    name: labelName[label],
    category: 'outcome',
    role: BLAME_LABEL_ROLES[label],
  }))

  const faultIndex = new Map<FaultType, number>(faults.map((fault, index) => [fault, index]))
  const labelIndex = new Map<BlameLabel, number>(
    labels.map((label, index) => [label, faults.length + index]),
  )

  const links = rows.flatMap((row) => {
    const source = faultIndex.get(row.fault_type)
    const target = labelIndex.get(row.label)
    if (source === undefined || target === undefined || row.count <= 0) return []
    return [{ source, target, value: row.count }]
  })

  return {
    nodes: [...faultNodes, ...labelNodes],
    links,
    total: links.reduce((sum, link) => sum + link.value, 0),
  }
}

/** The diagram in words, for the chart's text alternative. */
export function describeBlameFlow(rows: readonly SankeyFlow[], total: number): string {
  const byFault = new Map<FaultType, SankeyFlow[]>()
  for (const row of rows) {
    const existing = byFault.get(row.fault_type)
    byFault.set(row.fault_type, existing ? [...existing, row] : [row])
  }
  const sentences = [...byFault.entries()].map(([fault, flows]) => {
    const parts = flows
      .filter((flow) => flow.count > 0)
      .map((flow) => `${flow.count} ${BLAME_LABELS[flow.label].replace(/^[✓✕·]\s*/, '')}`)
    return `${FAULT_TYPE_LABELS[fault]}: ${parts.join(', ')}.`
  })
  return `Where Bisect's blame landed for ${total} labelled failures, by planted fault type. ${sentences.join(' ')}`
}
