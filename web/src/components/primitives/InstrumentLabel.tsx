import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface InstrumentLabelProps {
  readonly children: ReactNode
  readonly as?: 'span' | 'h2' | 'h3' | 'div'
  readonly className?: string
  readonly id?: string
}

/** Mono, uppercase, trailing underscore: `RECALL@M_`. Headers and canvases only. */
export function InstrumentLabel({
  children,
  as: Tag = 'span',
  className,
  id,
}: InstrumentLabelProps) {
  return (
    <Tag id={id} className={cn('label-instrument', className)}>
      {children}
      <span aria-hidden="true">_</span>
    </Tag>
  )
}
