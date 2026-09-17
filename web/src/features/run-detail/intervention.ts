/** The one-line form of an intervention: `reservation_id NM1VX1 -> ZFA04Y`. */
import type { InterventionDiff } from './api'

const ABSENT = 'absent'

export interface InterventionSummary {
  readonly field: string
  readonly before: string
  readonly after: string
}

/** The first field whose recorded value the intervention replaced, or null. */
export function interventionSummary(
  diff: InterventionDiff | null | undefined,
): InterventionSummary | null {
  if (!diff) return null
  const before = diff.original_tool_result
  const after = diff.replaced_tool_result
  const fields = [...new Set([...Object.keys(before), ...Object.keys(after)])]
  const changed = fields.find((field) => before[field] !== after[field])
  if (changed === undefined) return null
  return {
    field: changed,
    before: before[changed] ?? ABSENT,
    after: after[changed] ?? ABSENT,
  }
}
