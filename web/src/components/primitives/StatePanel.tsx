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
 * card is capped at 560px and centred, both ways, in the space the page has left.
 */
export function StatePanel({ variant = 'card', children, className }: StatePanelProps) {
  return (
    // The wrapper takes the height the page would otherwise leave blank, so the
    // card sits in the middle of it instead of under the header with a void below.
    <div className="grid min-h-[max(18rem,calc(100dvh-20rem))] place-items-center">
      <Panel variant={variant} className={cn('w-full max-w-[560px]', className)}>
        {children}
      </Panel>
    </div>
  )
}
