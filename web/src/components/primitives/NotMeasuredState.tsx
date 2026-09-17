import { cn } from '@/lib/utils'

import { CliCommand } from './CodeBlock'
import { InstrumentLabel } from './InstrumentLabel'

interface NotMeasuredStateProps {
  /** Instrument label, e.g. `benchmark`. */
  readonly label: string
  readonly title: string
  /** The server's own `not_available.reason`, shown verbatim — never paraphrased. */
  readonly reason: string
  /** The CLI command that would produce the measurement. */
  readonly command?: string
  readonly className?: string
}

const HATCH_CELLS = 10

/**
 * The `not_available` envelope, rendered honestly.
 *
 * Distinct from `EmptyState` (nothing recorded yet) and `ErrorState` (the request
 * failed): here the server answered, and its answer is "this is not measured".
 * It reuses the hatch that already means "not measured" on the heat stripe, and
 * it never shows a number, a zero or a placeholder chart in place of one.
 */
export function NotMeasuredState({
  label,
  title,
  reason,
  command,
  className,
}: NotMeasuredStateProps) {
  return (
    <div
      data-slot="not-measured-state"
      className={cn('flex flex-col items-start gap-4 py-6 sm:py-10', className)}
    >
      <div aria-hidden="true" className="flex items-end gap-1">
        {Array.from({ length: HATCH_CELLS }, (_, index) => (
          <span
            key={index}
            className="hatch h-8 w-5 rounded-step border border-line-strong sm:w-7"
          />
        ))}
      </div>
      <div className="flex max-w-prose flex-col gap-1.5">
        <InstrumentLabel>{label} · not measured</InstrumentLabel>
        <h2 className="text-h2 text-ink">{title}</h2>
        <p className="text-pretty text-ink-muted">
          The server has no measurement for this yet and will not invent one.
        </p>
        <p className="num text-small text-ink-muted">{reason}</p>
      </div>
      {command ? <CliCommand command={command} /> : null}
    </div>
  )
}
