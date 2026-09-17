import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import type { ApiError, ApiResult, ResponseMeta } from '@/api/client'
import { type NotAvailable, splitNotAvailable } from '@/api/payload'

import { ErrorState } from './ErrorState'
import { NotMeasuredState } from './NotMeasuredState'
import { Panel } from './Panel'
import { StatePanel } from './StatePanel'
import { LoadingRegion } from './Skeleton'

interface NotMeasuredCopy {
  readonly label: string
  readonly title: string
  /** The CLI command that would produce the measurement. */
  readonly command?: string
}

interface AsyncSectionProps<T> {
  readonly query: UseQueryResult<ApiResult<T | NotAvailable>, ApiError>
  /** What is loading, for the screen-reader status: "benchmark results". */
  readonly subject: string
  /** Shaped like the final layout, so loading is not a grey rectangle. */
  readonly skeleton: ReactNode
  readonly notMeasured: NotMeasuredCopy
  readonly children: (payload: T, meta: ResponseMeta) => ReactNode
}

/**
 * The four states every data page owes the reader: loading, failed, answered
 * with `not_available`, and answered with real numbers. Kept in one place so the
 * three pages that read a `T | NotAvailable` endpoint cannot drift apart.
 */
export function AsyncSection<T>({
  query,
  subject,
  skeleton,
  notMeasured,
  children,
}: AsyncSectionProps<T>) {
  if (query.isPending) {
    return (
      <LoadingRegion
        subject={subject}
        failureCount={query.failureCount}
        failureMessage={query.failureReason?.message}
      >
        {skeleton}
      </LoadingRegion>
    )
  }
  if (query.isError) {
    return (
      <StatePanel>
        <ErrorState
          title={`Cannot load ${subject}`}
          message={query.error.message}
          code={query.error.code}
          onRetry={() => void query.refetch()}
        />
      </StatePanel>
    )
  }
  const { payload, reason } = splitNotAvailable<T>(query.data.data)
  if (payload === null) {
    return (
      <Panel variant="canvas">
        <NotMeasuredState {...notMeasured} reason={reason ?? 'no reason given'} />
      </Panel>
    )
  }
  return <>{children(payload, query.data.meta)}</>
}
