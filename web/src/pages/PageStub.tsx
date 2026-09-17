import type { ReactNode } from 'react'

import { useMetaQuery } from '@/api/queries'
import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'
import { StatePanel } from '@/components/primitives/StatePanel'
import { LoadingRegion } from '@/components/primitives/Skeleton'

import { PageHeader } from './PageHeader'

export interface PageStubEmpty {
  readonly label: string
  readonly title: string
  readonly description: string
  readonly command: string
}

interface PageStubProps {
  readonly label: string
  readonly title: string
  readonly description: string
  readonly empty: PageStubEmpty
  /** The page's blueprint drawn in skeleton blocks, shown only while the API answers. */
  readonly skeleton: ReactNode
}

/**
 * Round-0 page: shell + designed states, no numbers. The skeleton is tied to a
 * real request (`/api/meta`), so a shimmer never stands in for work that is not happening.
 */
export function PageStub({ label, title, description, empty, skeleton }: PageStubProps) {
  const meta = useMetaQuery()
  return (
    <>
      <PageHeader label={label} title={title} description={description} />
      {meta.isPending ? (
        <LoadingRegion subject={title}>{skeleton}</LoadingRegion>
      ) : meta.isError ? (
        <StatePanel>
          <ErrorState
            title="Cannot reach the Bisect server"
            message={meta.error.message}
            code={meta.error.code}
            onRetry={() => void meta.refetch()}
          />
        </StatePanel>
      ) : (
        <Panel variant="canvas">
          <EmptyState {...empty} />
        </Panel>
      )}
    </>
  )
}
