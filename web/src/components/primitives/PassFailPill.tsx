import { Check, X } from 'lucide-react'

import { cn } from '@/lib/utils'

export type Outcome = 'pass' | 'fail'

interface PassFailPillProps {
  readonly outcome: Outcome
  /** Overrides the default "Pass" / "Fail" label, e.g. "9/12 pass". */
  readonly label?: string
  readonly size?: 'sm' | 'md'
  readonly className?: string
}

const OUTCOME_STYLES: Readonly<Record<Outcome, string>> = {
  pass: 'bg-pass-tint text-pass border-pass/40',
  fail: 'bg-fail-tint text-fail border-fail/40',
}

const DEFAULT_LABELS: Readonly<Record<Outcome, string>> = { pass: 'Pass', fail: 'Fail' }

/** Outcome is never colour alone: the glyph and the word are always present. */
export function PassFailPill({ outcome, label, size = 'md', className }: PassFailPillProps) {
  const Glyph = outcome === 'pass' ? Check : X
  return (
    <span
      data-outcome={outcome}
      className={cn(
        'inline-flex items-center gap-1 rounded-pill border font-medium whitespace-nowrap',
        size === 'sm' ? 'h-5 px-1.5 text-[11px]' : 'h-6 px-2 text-small',
        OUTCOME_STYLES[outcome],
        className,
      )}
    >
      <Glyph
        aria-hidden="true"
        className={size === 'sm' ? 'size-3' : 'size-3.5'}
        strokeWidth={2.75}
      />
      {label ?? DEFAULT_LABELS[outcome]}
    </span>
  )
}
