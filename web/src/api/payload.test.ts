import { describe, expect, test } from 'vitest'

import { isNotAvailable, splitNotAvailable } from './payload'

/** The two shapes any of these endpoints can answer with. */
const MEASURED = { accuracy: 0.9651, n: 86 }
const NOT_MEASURED = {
  status: 'not_available',
  reason: 'no eval results yet (data/eval.parquet not found)',
}

describe('isNotAvailable', () => {
  test('recognises the server’s not_available payload', () => {
    expect(isNotAvailable(NOT_MEASURED)).toBe(true)
  })

  test('leaves a real payload alone', () => {
    expect(isNotAvailable(MEASURED)).toBe(false)
  })

  test('does not fire on a payload that has its own status field', () => {
    // RunSummary and RunDetail both carry `status: "recording" | "complete"`,
    // so a loose check on the key alone would hide every finished run.
    expect(isNotAvailable({ run_id: 'brief-12-step', status: 'complete' })).toBe(false)
    expect(isNotAvailable({ run_id: 'run-042', status: 'recording' })).toBe(false)
  })

  test('is safe on anything that is not an object', () => {
    expect(isNotAvailable(null)).toBe(false)
    expect(isNotAvailable(undefined)).toBe(false)
    expect(isNotAvailable('not_available')).toBe(false)
    expect(isNotAvailable(0)).toBe(false)
    expect(isNotAvailable([])).toBe(false)
  })
})

describe('splitNotAvailable', () => {
  test('hands back the payload and no reason when the server measured it', () => {
    // Act
    const split = splitNotAvailable<typeof MEASURED>(MEASURED)

    // Assert — the same object, so a caller can compare by reference.
    expect(split.payload).toBe(MEASURED)
    expect(split.reason).toBeNull()
  })

  test('hands back no payload and the server’s own reason when it did not', () => {
    // Act
    const split = splitNotAvailable<typeof MEASURED>(NOT_MEASURED)

    // Assert — null, never a zero or an empty object a page could draw.
    expect(split.payload).toBeNull()
    expect(split.reason).toBe(NOT_MEASURED.reason)
  })

  test('treats a run payload with status "complete" as measured', () => {
    // Arrange
    const run = { run_id: 'brief-12-step', status: 'complete' as const }

    // Act / Assert
    expect(splitNotAvailable<typeof run>(run).payload).toBe(run)
  })
})
