import { cn } from '@/lib/utils'

import { InstrumentLabel } from './InstrumentLabel'

interface DiffBlockProps {
  /** What the tape recorded. */
  readonly before: string
  /** What the intervention replaced it with. */
  readonly after: string
  readonly label?: string
  readonly className?: string
}

interface DiffLineProps {
  readonly kind: 'removed' | 'added'
  readonly text: string
}

const LINE_STYLES: Readonly<Record<DiffLineProps['kind'], string>> = {
  // Old = what the tape said (slate). New = the measured intervention (cyan).
  removed: 'bg-tape-tint border-tape',
  added: 'bg-measure-tint border-measure',
}

function DiffLine({ kind, text }: DiffLineProps) {
  const removed = kind === 'removed'
  const Tag = removed ? 'del' : 'ins'
  return (
    <Tag className={cn('flex gap-3 border-l-2 px-3 py-1 no-underline', LINE_STYLES[kind])}>
      <span aria-hidden="true" className="w-2 shrink-0 text-ink-muted select-none">
        {removed ? '−' : '+'}
      </span>
      <span className="sr-only">{removed ? 'Recorded on tape: ' : 'Replaced with: '}</span>
      <span className={cn('min-w-0 break-all', removed ? 'text-ink-muted' : 'text-ink')}>
        {text}
      </span>
    </Tag>
  )
}

/** `− old / + new` for one intervention. Sign glyphs always present; colour is secondary. */
export function DiffBlock({ before, after, label, className }: DiffBlockProps) {
  return (
    <figure
      className={cn(
        'min-w-0 overflow-hidden rounded-chart border border-line bg-ground',
        className,
      )}
    >
      {label ? (
        <figcaption className="flex h-9 items-center border-b border-line px-3">
          <InstrumentLabel>{label}</InstrumentLabel>
        </figcaption>
      ) : null}
      <div className="font-mono text-small leading-[1.6]">
        <DiffLine kind="removed" text={before} />
        <DiffLine kind="added" text={after} />
      </div>
    </figure>
  )
}
