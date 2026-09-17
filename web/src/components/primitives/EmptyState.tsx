import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { CliCommand } from './CodeBlock'
import { InstrumentLabel } from './InstrumentLabel'

interface EmptyStateProps {
  /** Instrument label, e.g. `no runs recorded`. */
  readonly label: string
  readonly title: string
  readonly description: string
  /** The CLI command that produces the missing data. */
  readonly command?: string
  readonly children?: ReactNode
  readonly className?: string
}

const EMPTY_TAPE_CELLS = 12

/** An empty tape: twelve unrecorded cells. No fake numbers, ever. */
function EmptyTape() {
  return (
    <div aria-hidden="true" className="flex items-center gap-1">
      {Array.from({ length: EMPTY_TAPE_CELLS }, (_, index) => (
        <span
          key={index}
          className="h-7 w-5 rounded-step border border-dashed border-line-strong sm:w-6"
        />
      ))}
    </div>
  )
}

export function EmptyState({
  label,
  title,
  description,
  command,
  children,
  className,
}: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      className={cn('flex flex-col items-start gap-4 py-6 sm:py-10', className)}
    >
      <EmptyTape />
      <div className="flex max-w-prose flex-col gap-1.5">
        <InstrumentLabel>{label}</InstrumentLabel>
        <h2 className="text-h2 text-ink">{title}</h2>
        <p className="text-pretty text-ink-muted">{description}</p>
      </div>
      {command ? <CliCommand command={command} /> : null}
      {children}
    </div>
  )
}
