import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface KbdProps {
  readonly children: ReactNode
  readonly className?: string
}

export function Kbd({ children, className }: KbdProps) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded-step border border-line-strong bg-elevated px-1 font-mono text-[11px] leading-none font-medium text-ink-muted',
        className,
      )}
    >
      {children}
    </kbd>
  )
}
