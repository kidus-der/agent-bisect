import { motion } from 'motion/react'
import { Tabs as TabsPrimitive } from 'radix-ui'
import { type ReactNode, useId, useState } from 'react'

import { layoutIds, useSpringTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

export interface TabItem {
  readonly value: string
  readonly label: string
  readonly content: ReactNode
}

interface TabsProps {
  readonly items: readonly TabItem[]
  readonly defaultValue?: string
  readonly value?: string
  readonly onValueChange?: (value: string) => void
  /** Accessible name for the tab list. */
  readonly label: string
  readonly className?: string
}

/** Line tabs. The active underline is one shared-layout element that slides. */
export function Tabs({ items, defaultValue, value, onValueChange, label, className }: TabsProps) {
  const groupId = useId()
  const transition = useSpringTransition('snap')
  const [internal, setInternal] = useState(defaultValue ?? items[0]?.value ?? '')
  const active = value ?? internal

  const handleChange = (next: string): void => {
    setInternal(next)
    onValueChange?.(next)
  }

  return (
    <TabsPrimitive.Root value={active} onValueChange={handleChange} className={className}>
      <TabsPrimitive.List aria-label={label} className="flex gap-1 border-b border-line">
        {items.map((item) => (
          <TabsPrimitive.Trigger
            key={item.value}
            value={item.value}
            className={cn(
              'relative -mb-px h-9 cursor-pointer rounded-control px-3 text-small font-medium',
              item.value === active ? 'text-ink' : 'text-ink-muted hover:text-ink',
            )}
          >
            {item.label}
            {item.value === active ? (
              <motion.span
                layoutId={layoutIds.tabIndicator(groupId)}
                transition={transition}
                className="absolute inset-x-2 -bottom-px h-0.5 bg-ink"
              />
            ) : null}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((item) => (
        <TabsPrimitive.Content key={item.value} value={item.value} className="pt-4">
          {item.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  )
}
