import { Tooltip as TooltipPrimitive } from 'radix-ui'
import type { ReactElement, ReactNode } from 'react'

interface TooltipProps {
  readonly content: ReactNode
  /** A single focusable element; the tooltip is its description. */
  readonly children: ReactElement
  readonly side?: 'top' | 'right' | 'bottom' | 'left'
}

const SIDE_OFFSET_PX = 6

export const TooltipProvider = TooltipPrimitive.Provider

/** Flat elevated chip, hairline border, no arrow, no shadow. */
export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={SIDE_OFFSET_PX}
          className="z-(--z-toast) max-w-xs rounded-control border border-line-strong bg-elevated px-2 py-1 text-small text-ink"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}
