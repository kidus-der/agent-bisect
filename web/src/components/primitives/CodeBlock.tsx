import { cn } from '@/lib/utils'

import { CopyButton } from './CopyButton'
import { InstrumentLabel } from './InstrumentLabel'

interface CodeBlockProps {
  readonly code: string
  /** Instrument label above the block, e.g. `payload`. */
  readonly label?: string
  readonly copyable?: boolean
  readonly className?: string
}

export function CodeBlock({ code, label, copyable = true, className }: CodeBlockProps) {
  return (
    <figure className={cn('min-w-0 rounded-chart border border-line bg-ground', className)}>
      {label || copyable ? (
        <figcaption className="flex h-9 items-center justify-between border-b border-line pr-1 pl-3">
          {label ? <InstrumentLabel>{label}</InstrumentLabel> : <span />}
          {copyable ? <CopyButton text={code} subject={label ?? 'code'} /> : null}
        </figcaption>
      ) : null}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be keyboard reachable (axe: scrollable-region-focusable) */}
      <pre tabIndex={0} className="overflow-x-auto p-3 font-mono text-small leading-[1.6] text-ink">
        <code>{code}</code>
      </pre>
    </figure>
  )
}

interface CliCommandProps {
  readonly command: string
  readonly className?: string
}

/** One copyable shell line: `$ bisect record --domain airline --tasks 0-19`. */
export function CliCommand({ command, className }: CliCommandProps) {
  return (
    <div
      className={cn(
        'inline-flex max-w-full items-center gap-2 rounded-control border border-line bg-ground py-0.5 pr-0.5 pl-3',
        className,
      )}
    >
      <span aria-hidden="true" className="font-mono text-ink-muted select-none">
        $
      </span>
      <code className="min-w-0 font-mono text-small break-words text-ink sm:overflow-x-auto sm:whitespace-nowrap">
        {command}
      </code>
      <CopyButton text={command} subject="command" />
    </div>
  )
}
