import { Check, Copy, X } from 'lucide-react'

import { type CopyStatus, useCopy } from '@/lib/useCopy'
import { cn } from '@/lib/utils'

interface CopyButtonProps {
  readonly text: string
  /** What is being copied, for the accessible name: "command", "JSON". */
  readonly subject: string
  readonly className?: string
}

const STATUS_LABELS: Readonly<Record<CopyStatus, string>> = {
  idle: 'Copy',
  copied: 'Copied',
  failed: 'Copy failed',
}

export function CopyButton({ text, subject, className }: CopyButtonProps) {
  const { status, copy } = useCopy()
  const Icon = status === 'copied' ? Check : status === 'failed' ? X : Copy
  return (
    <button
      type="button"
      onClick={() => void copy(text)}
      aria-label={`${STATUS_LABELS[status]} ${subject}`}
      className={cn(
        'relative inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-control text-ink-muted hover:bg-elevated hover:text-ink',
        // 40px hit area around a 28px glyph button.
        'after:absolute after:-inset-1.5',
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      <span aria-live="polite" className="sr-only">
        {status === 'idle' ? '' : STATUS_LABELS[status]}
      </span>
    </button>
  )
}
