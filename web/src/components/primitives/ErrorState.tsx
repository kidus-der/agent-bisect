import { RotateCw } from 'lucide-react'

import { cn } from '@/lib/utils'

import { InstrumentLabel } from './InstrumentLabel'

interface ErrorStateProps {
  readonly title?: string
  readonly message: string
  /** Machine code from the API envelope, shown as a mono token. */
  readonly code?: string
  readonly onRetry?: () => void
  readonly className?: string
}

export function ErrorState({
  title = 'Something failed to load',
  message,
  code,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      data-slot="error-state"
      className={cn('flex flex-col items-start gap-4 py-2 sm:py-4', className)}
    >
      <div className="flex max-w-prose flex-col gap-1.5">
        <InstrumentLabel>{code ? `error · ${code}` : 'error'}</InstrumentLabel>
        <h2 className="text-h2 text-ink">{title}</h2>
        <p className="text-pretty text-ink-muted">{message}</p>
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-control border border-line-strong bg-elevated px-3 text-small font-medium text-ink hover:border-ink-muted"
        >
          <RotateCw aria-hidden="true" className="size-3.5" />
          Retry
        </button>
      ) : null}
    </div>
  )
}
