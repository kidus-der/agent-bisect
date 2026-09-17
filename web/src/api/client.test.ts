import { afterEach, describe, expect, test, vi } from 'vitest'

import { ApiError, apiFetch, availableOrNull, isNotAvailable } from './client'

const META = { simulated: true, data_source: 'fixture' }

function mockFetch(response: Partial<Response> | Error): ReturnType<typeof vi.fn> {
  const mock = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  )
  vi.stubGlobal('fetch', mock)
  return mock
}

function jsonResponse(body: unknown, status = 200): Partial<Response> {
  return { ok: status < 400, status, json: () => Promise.resolve(body) }
}

async function captureError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('expected apiFetch to throw')
}

afterEach(() => vi.unstubAllGlobals())

describe('apiFetch', () => {
  test('unwraps a successful envelope into data + meta', async () => {
    const fetchMock = mockFetch(
      jsonResponse({ success: true, data: { status: 'ok' }, error: null, meta: META }),
    )
    const result = await apiFetch<{ status: string }>('/health')
    expect(result).toEqual({ data: { status: 'ok' }, meta: META })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  test('throws a typed api error carrying the envelope code and message', async () => {
    mockFetch(
      jsonResponse(
        {
          success: false,
          data: null,
          error: { code: 'run_not_found', message: 'No such run.' },
          meta: META,
        },
        404,
      ),
    )
    const error = await captureError(apiFetch('/runs/nope'))
    expect(error).toMatchObject({
      kind: 'api',
      code: 'run_not_found',
      message: 'No such run.',
      status: 404,
    })
    expect(error.retryable).toBe(false)
  })

  test('maps a rejected fetch to a retryable network error', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    const error = await captureError(apiFetch('/meta'))
    expect(error).toMatchObject({ kind: 'network', code: 'network_error' })
    expect(error.message).toMatch(/bisect serve/)
    expect(error.retryable).toBe(true)
  })

  test('a request that outlives the timeout fails as a retryable timeout, not a generic network error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new DOMException('The operation timed out.', 'TimeoutError'))),
    )
    const error = await captureError(apiFetch('/overview'))
    expect(error).toMatchObject({ kind: 'network', code: 'timeout' })
    expect(error.message).toMatch(/did not answer within 8 s/)
    expect(error.retryable).toBe(true)
  })

  test("every request carries an abort signal, merged with the caller's", async () => {
    const fetchMock = mockFetch(jsonResponse({ success: true, data: {}, error: null, meta: META }))
    const controller = new AbortController()
    await apiFetch('/meta', { signal: controller.signal })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
    expect(init?.signal).toBeInstanceOf(AbortSignal)
    controller.abort()
    expect(init?.signal?.aborted).toBe(true)
  })

  test('maps a non-JSON 5xx (dev proxy with the API down) to a retryable http error', async () => {
    mockFetch({
      ok: false,
      status: 502,
      json: () => Promise.reject(new SyntaxError('Unexpected token <')),
    })
    const error = await captureError(apiFetch('/meta'))
    expect(error).toMatchObject({ kind: 'http', code: 'http_error', status: 502 })
    expect(error.retryable).toBe(true)
  })

  test('rejects a 200 whose body is not an envelope', async () => {
    mockFetch(jsonResponse({ hello: 'world' }))
    const error = await captureError(apiFetch('/meta'))
    expect(error).toMatchObject({ kind: 'envelope', code: 'invalid_envelope' })
  })

  test('rejects a success envelope without a valid meta block', async () => {
    mockFetch(jsonResponse({ success: true, data: {}, error: null, meta: { simulated: 'yes' } }))
    const error = await captureError(apiFetch('/meta'))
    expect(error).toMatchObject({ kind: 'envelope', code: 'invalid_meta' })
  })

  test('falls back to a generic code when a failed envelope has no error block', async () => {
    mockFetch(jsonResponse({ success: false, data: null, error: null, meta: META }, 500))
    const error = await captureError(apiFetch('/meta'))
    expect(error).toMatchObject({ kind: 'api', code: 'unknown_error', status: 500 })
  })
})

describe('isNotAvailable', () => {
  test('recognises the server’s not_available placeholder', () => {
    expect(isNotAvailable({ status: 'not_available', reason: 'no recordings yet' })).toBe(true)
  })

  test('treats real payloads and nullish values as available', () => {
    expect(isNotAvailable({ status: 'complete' })).toBe(false)
    expect(isNotAvailable(null)).toBe(false)
    expect(isNotAvailable(undefined)).toBe(false)
    expect(isNotAvailable('not_available')).toBe(false)
  })
})

describe('availableOrNull', () => {
  test('returns the payload when the server answered with one', () => {
    const payload = { runs_recorded: 266 }
    expect(availableOrNull(payload)).toBe(payload)
  })

  test('narrows not_available to null so no number can be rendered from it', () => {
    expect(availableOrNull({ status: 'not_available', reason: 'no recordings yet' })).toBeNull()
    expect(availableOrNull(null)).toBeNull()
  })
})
