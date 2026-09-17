/**
 * How the five evaluated methods are named, ordered and coloured.
 *
 * Colour follows direction.md §3: cyan is measurement (Bisect's own replay),
 * violet is the LLM judge, slate is a baseline carrying no emphasis. Two methods
 * share slate, so the ablation also carries a hatch pattern and every bar carries
 * its own direct label — the role is never left to colour alone.
 */
import type { MethodName } from './api'
import type { RoleName } from '@/design/tokens'

export type MethodKind = 'bisect' | 'judge' | 'baseline' | 'ablation'

export interface MethodMeta {
  readonly name: MethodName
  readonly label: string
  /** Mono token used in the dense heatmap header, where the full label will not fit. */
  readonly shortLabel: string
  readonly kind: MethodKind
  readonly role: RoleName
  /** One line: what this method actually does. */
  readonly description: string
  /** Hatched fill, so the ablation is distinguishable from the live-rerun baseline. */
  readonly hatched: boolean
}

/** Display order: the product first, then what it is measured against. */
export const METHOD_ORDER: readonly MethodName[] = [
  'bisect',
  'judge_step_by_step',
  'judge_all_at_once',
  'rerun_live',
  'no_control',
]

const METHOD_META: Readonly<Record<MethodName, MethodMeta>> = {
  bisect: {
    name: 'bisect',
    label: 'Bisect',
    shortLabel: 'bisect',
    kind: 'bisect',
    role: 'measure',
    description: 'Replay to k from tape, fix one step, re-run N times against a shared control.',
    hatched: false,
  },
  judge_step_by_step: {
    name: 'judge_step_by_step',
    label: 'Judge, step by step',
    shortLabel: 'judge/step',
    kind: 'judge',
    role: 'judge',
    description: 'One LLM call per step, asking whether that step is the cause.',
    hatched: false,
  },
  judge_all_at_once: {
    name: 'judge_all_at_once',
    label: 'Judge, all at once',
    shortLabel: 'judge/all',
    kind: 'judge',
    role: 'judge',
    description: 'One LLM call over the whole trace, asking which step is the cause.',
    hatched: false,
  },
  rerun_live: {
    name: 'rerun_live',
    label: 'Re-run live',
    shortLabel: 'rerun',
    kind: 'baseline',
    role: 'tape',
    description: 'No tape and no snapshot: replays every prefix live before intervening.',
    hatched: false,
  },
  no_control: {
    name: 'no_control',
    label: 'No control (ablation)',
    shortLabel: 'no ctrl',
    kind: 'ablation',
    role: 'tape',
    description: 'Bisect with the control arm removed — blames a step for its luck.',
    hatched: true,
  },
}

export function methodMeta(name: MethodName): MethodMeta {
  return METHOD_META[name]
}

export function methodLabel(name: MethodName): string {
  return METHOD_META[name].label
}

/** Sorts any method-keyed rows into the display order above. */
export function byMethodOrder<T extends { readonly method: MethodName }>(
  rows: readonly T[],
): readonly T[] {
  return [...rows].sort((a, b) => METHOD_ORDER.indexOf(a.method) - METHOD_ORDER.indexOf(b.method))
}

export const FAULT_TYPE_LABELS = {
  wrong_value: 'wrong value',
  missing_field: 'missing field',
  stale_record: 'stale record',
  tool_error: 'tool error text',
} as const

/** Short forms for the sankey's outside labels, which have no room on a phone. */
export const FAULT_TYPE_SHORT = {
  wrong_value: 'wrong',
  missing_field: 'missing',
  stale_record: 'stale',
  tool_error: 'tool err',
} as const

export const POSITION_LABELS = { early: 'early', middle: 'middle', late: 'late' } as const
export const POSITION_ORDER = ['early', 'middle', 'late'] as const

/** Where the blamed step landed relative to the planted one. */
export const BLAME_LABELS = {
  exact: '✓ exact step',
  earlier: '✕ an earlier step',
  later: '✕ a later step',
  none: '· no step blamed',
} as const
export const BLAME_LABELS_SHORT = {
  exact: '✓ exact',
  earlier: '✕ earlier',
  later: '✕ later',
  none: '· none',
} as const

export const BLAME_LABEL_ORDER = ['exact', 'earlier', 'later', 'none'] as const

/**
 * Only `exact` is a hit. `earlier` and `later` are both misses and share the fail
 * role; their own labels, which are always drawn, say which way they missed.
 * `none` is the quiet "nothing was concluded" state, so it takes from-tape slate.
 */
export const BLAME_LABEL_ROLES: Readonly<Record<keyof typeof BLAME_LABELS, RoleName>> = {
  exact: 'pass',
  earlier: 'fail',
  later: 'fail',
  none: 'tape',
}
