/**
 * `not_available` narrowing.
 *
 * A field the server cannot answer yet comes back as HTTP 200 with
 * `data = {"status": "not_available", "reason": "..."}` rather than a
 * fabricated number (api-contract.md). Every page that reads such an endpoint
 * has to tell that apart from a real payload before it draws anything.
 */
import type { Schemas } from './client'

export type NotAvailable = Readonly<Schemas['NotAvailable']>

const NOT_AVAILABLE_STATUS = 'not_available'

export function isNotAvailable(data: unknown): data is NotAvailable {
  return (
    typeof data === 'object' &&
    data !== null &&
    'status' in data &&
    (data as { status: unknown }).status === NOT_AVAILABLE_STATUS
  )
}

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
