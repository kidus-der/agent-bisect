import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { Panel, type PanelVariant } from './Panel'

interface StatePanelProps {
  readonly variant?: PanelVariant
  readonly children: ReactNode
  readonly className?: string
}

/**
 * Page-level error and not-found states. A message is ~400px of content, so its
 * card is capped at 560px and centred instead of stretching across the grid
 * with a hole in it.
 */
export function StatePanel({ variant = 'card', children, className }: StatePanelProps) {
  return (
    <Panel
      variant={variant}
      className={cn('mx-auto mt-4 w-full max-w-[560px] lg:mt-10', className)}
    >
      {children}
    </Panel>
  )
}
