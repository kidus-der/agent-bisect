import { type ErrorComponentProps, Link } from '@tanstack/react-router'

import { ApiError } from '@/api/client'
import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel } from '@/components/primitives/Panel'
import { LoadingRegion, Skeleton } from '@/components/primitives/Skeleton'

/** Per-route error boundary: a failing page never takes the shell down with it. */
export function RouteError({ error, reset }: ErrorComponentProps) {
  const apiError = error instanceof ApiError ? error : undefined
  return (
    <Panel variant="card">
      <ErrorState
        title="This page failed to render"
        message={error instanceof Error ? error.message : 'An unexpected error occurred.'}
        code={apiError?.code}
        onRetry={reset}
      />
    </Panel>
  )
}

export function RouteNotFound() {
  return (
    <Panel variant="card">
      <EmptyState
        label="404 · no such route"
        title="Nothing is recorded at this address"
        description="The page may have moved, or the link points at a run that was never recorded."
      >
        <Link to="/" className="text-small font-medium text-ink underline underline-offset-4">
          Back to Overview
        </Link>
      </EmptyState>
    </Panel>
  )
}

/** Shown while a route's code chunk loads: a real wait, so a skeleton is honest here. */
export function RoutePending() {
  return (
    <LoadingRegion subject="page">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-8 w-56" />
      <Skeleton className="mt-8 h-64 w-full rounded-card" />
    </LoadingRegion>
  )
}
