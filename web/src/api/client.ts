/**
 * Typed fetch for the Bisect JSON API. Every endpoint returns the envelope
 * `{ success, data, error, meta }` (agent_bisect/server/schemas_common.py);
 * `apiFetch` unwraps it and throws a typed `ApiError` for anything else.
 */
import type { components } from './schema'

/** Generated from agent_bisect/server/openapi.json by `npm run api:types`. */
export type Schemas = components['schemas']

export type DataSource = Schemas['ResponseMeta']['data_source']
export type ResponseMeta = Readonly<Schemas['ResponseMeta']>
export type ApiErrorInfo = Readonly<Schemas['ErrorInfo']>

export interface ApiResult<T> {
  readonly data: T
  readonly meta: ResponseMeta
}

export type ApiErrorKind = 'network' | 'http' | 'envelope' | 'api'

interface ApiErrorInit {
  readonly kind: ApiErrorKind
  readonly code: string
  readonly message: string
  readonly status?: number
  readonly cause?: unknown
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly code: string
  readonly status: number | undefined

  constructor({ kind, code, message, status, cause }: ApiErrorInit) {
    super(message, { cause })
    this.name = 'ApiError'
    this.kind = kind
    this.code = code
    this.status = status
  }

  /** Transient failures are worth a retry; a 4xx or a malformed body is not. */
  get retryable(): boolean {
    if (this.kind === 'network') return true
    return this.kind === 'http' && this.status !== undefined && this.status >= 500
  }
}

const API_PREFIX = '/api'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isResponseMeta(value: unknown): value is ResponseMeta {
  return (
    isRecord(value) &&
    typeof value.simulated === 'boolean' &&
    (value.data_source === 'fixture' || value.data_source === 'real')
  )
}

function isErrorInfo(value: unknown): value is ApiErrorInfo {
  return isRecord(value) && typeof value.code === 'string' && typeof value.message === 'string'
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch (cause) {
    // A non-JSON 5xx is what the dev proxy returns when `bisect serve` is down.
    throw new ApiError({
      kind: response.ok ? 'envelope' : 'http',
      code: response.ok ? 'invalid_json' : 'http_error',
      message: response.ok
        ? 'The server answered without a JSON body.'
        : `The Bisect server answered ${response.status}. Is \`bisect serve\` running?`,
      status: response.status,
      cause,
    })
  }
}

function unwrapEnvelope<T>(body: unknown, status: number): ApiResult<T> {
  if (!isRecord(body) || typeof body.success !== 'boolean') {
    throw new ApiError({
      kind: status >= 400 ? 'http' : 'envelope',
      code: 'invalid_envelope',
      message: `The server answered ${status} with an unexpected response shape.`,
      status,
    })
  }
  if (!body.success) {
    const info = isErrorInfo(body.error)
      ? body.error
      : { code: 'unknown_error', message: `Request failed with status ${status}.` }
    throw new ApiError({ kind: 'api', code: info.code, message: info.message, status })
  }
  if (!isResponseMeta(body.meta)) {
    throw new ApiError({
      kind: 'envelope',
      code: 'invalid_meta',
      message: 'The response is missing its meta block (simulated / data_source).',
      status,
    })
  }
  // The payload shape is the endpoint's contract; callers pass the generated type.
  return { data: body.data as T, meta: body.meta }
}

/** Fetch `/api${path}` and unwrap the envelope. Throws `ApiError`. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const url = `${API_PREFIX}${path}`
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch (cause) {
    throw new ApiError({
      kind: 'network',
      code: 'network_error',
      message: 'Cannot reach the Bisect server. Is `bisect serve` running?',
      cause,
    })
  }
  const body = await readJson(response)
  return unwrapEnvelope<T>(body, response.status)
}
