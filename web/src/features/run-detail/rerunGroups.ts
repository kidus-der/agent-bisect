/**
 * The treated-vs-control matrix as rows: one arm of one step per row, in the
 * order the estimator ran them.
 */
import type { RerunRow } from './api'

/** The sequential estimator looks after every four re-runs; the dots are grouped to match. */
export const BATCH_SIZE = 4

export type Arm = RerunRow['arm']

export interface RerunGroup {
  readonly key: string
  readonly arm: Arm
  readonly step: number
  readonly rows: readonly RerunRow[]
  readonly passed: number
  /** One control arm standing in for every treated step (`control_mode: shared`). */
  readonly shared: boolean
}

function keyOf(arm: Arm, step: number): string {
  return `${arm}-${step}`
}

export function groupReruns(rows: readonly RerunRow[]): readonly RerunGroup[] {
  const buckets = new Map<string, RerunRow[]>()
  for (const row of rows) {
    const key = keyOf(row.arm, row.step)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(row)
    else buckets.set(key, [row])
  }
  const groups = [...buckets.entries()].map(([key, bucket]) => ({
    key,
    arm: bucket[0]?.arm ?? 'treated',
    step: bucket[0]?.step ?? 0,
    rows: bucket as readonly RerunRow[],
    passed: bucket.filter((row) => row.passed).length,
    shared: false,
  }))
  const controls = groups.filter((group) => group.arm === 'control')
  const treated = groups.filter((group) => group.arm === 'treated')
  const shared = controls.length === 1 && treated.length > 1
  const byStep = (a: RerunGroup, b: RerunGroup): number => a.step - b.step
  return [...controls.map((group) => ({ ...group, shared })).sort(byStep), ...treated.sort(byStep)]
}

export function batchesOf<T>(rows: readonly T[], size: number): readonly (readonly T[])[] {
  const batches: T[][] = []
  for (let index = 0; index < rows.length; index += size) {
    batches.push(rows.slice(index, index + size))
  }
  return batches
}
