import type { ScenarioRow } from './api'

/**
 * What a gate check is identified by, and what a scenario's change is when
 * there is nothing to compare against.
 *
 * In real mode a gate run compares two git refs, which need not be a pull
 * request, so `pr_number` can be absent; the check's `title` already reads
 * `base_ref → head_ref` in that case. A scenario that is new in head has no
 * base run, so it has no change — reporting `head - 0` would invent one.
 */
export function checkBadge(prNumber: number | null): string | null {
  return prNumber === null ? null : `#${prNumber}`
}

export function scenarioDelta(row: ScenarioRow): number | null {
  if (row.base_pass_rate === null) return null
  return row.head_pass_rate - row.base_pass_rate
}
