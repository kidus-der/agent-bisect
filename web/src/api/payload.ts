/**
 * `not_available` helpers built on the client's single narrowing.
 *
 * A field the server cannot answer yet comes back as HTTP 200 with
 * `data = {"status": "not_available", "reason": "..."}` rather than a
 * fabricated number (api-contract.md). `isNotAvailable` and `availableOrNull`
 * live in `./client` beside the envelope they narrow; they are re-exported here
 * so the pages that already import them from this module keep working, and so
 * there is exactly one implementation to get right.
 */
export { type NotAvailable, availableOrNull, isNotAvailable } from './client'

import { type NotAvailable, isNotAvailable } from './client'

/**
 * Splits an endpoint's payload into "measured" and "not measured yet". `payload`
 * is `null` exactly when the server said it has nothing, and `reason` carries the
 * server's own explanation so the UI never has to guess one.
 */
export interface MeasuredPayload<T> {
  readonly payload: T | null
  readonly reason: string | null
}

export function splitNotAvailable<T>(data: T | NotAvailable): MeasuredPayload<T> {
  if (isNotAvailable(data)) return { payload: null, reason: data.reason }
  return { payload: data, reason: null }
}
