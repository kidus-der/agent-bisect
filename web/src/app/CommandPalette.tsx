import { useNavigate } from '@tanstack/react-router'
import { Command } from 'cmdk'
import { Search } from 'lucide-react'
import { motion } from 'motion/react'
import { Dialog } from 'radix-ui'
import { useState } from 'react'

import { Kbd } from '@/components/primitives/Kbd'
import { useSpringTransition } from '@/design/motion'
import { toggleTheme } from '@/design/theme'
import { copyText } from '@/lib/useCopy'

import { PALETTE_GROUPS, PALETTE_ITEMS, type PaletteItem } from './paletteItems'

const DETAIL_FADE_SECONDS = 0.1

interface CommandPaletteProps {
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
}

function DetailPane({ item }: { readonly item: PaletteItem | undefined }) {
  if (!item) return null
  const Icon = item.icon
  return (
    <motion.aside
      // Cross-fades on selection change; the list itself filters with no animation.
      key={item.id}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: DETAIL_FADE_SECONDS }}
      aria-hidden="true"
      className="hidden w-64 shrink-0 flex-col gap-3 border-l border-line p-4 md:flex"
    >
      <span className="inline-flex size-10 items-center justify-center rounded-kpi border border-line-strong bg-surface text-ink">
        <Icon className="size-5" />
      </span>
      <div className="flex flex-col gap-1">
        <span className="label-instrument">{item.group}_</span>
        <span className="text-h3 text-ink">{item.label}</span>
      </div>
      <p className="text-small text-pretty text-ink-muted">{item.detail}</p>
      <code className="rounded-control border border-line bg-ground px-2 py-1.5 font-mono text-small break-all text-ink">
        {item.token}
      </code>
    </motion.aside>
  )
}

/** ⌘K. Raycast layout: filter input, result list, detail preview. Filtering is instant. */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const transition = useSpringTransition('snap')
  const [selectedId, setSelectedId] = useState<string>(PALETTE_ITEMS[0]?.id ?? '')
  const selected = PALETTE_ITEMS.find((item) => item.id === selectedId)

  const run = (item: PaletteItem): void => {
    onOpenChange(false)
    if (item.action.kind === 'navigate') {
      void navigate({ to: item.action.to })
    } else if (item.action.kind === 'toggle-theme') {
      toggleTheme()
    } else {
      void copyText(item.action.text)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-(--z-overlay) bg-(--bx-scrim) backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-[14vh] left-1/2 z-(--z-palette) w-[min(720px,calc(100vw-24px))] -translate-x-1/2 outline-none"
        >
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={transition}
            className="overflow-hidden rounded-modal border border-line-strong bg-elevated shadow-glow-chrome"
          >
            <Command
              label="Command palette"
              value={selectedId}
              onValueChange={setSelectedId}
              loop
              className="flex flex-col"
            >
              <div className="flex h-12 items-center gap-2.5 border-b border-line px-4">
                <Search aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
                <Command.Input
                  placeholder="Jump to a page or run a command"
                  className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-muted"
                />
                <Kbd>esc</Kbd>
              </div>
              <div className="flex min-h-0">
                <Command.List className="max-h-[min(420px,56vh)] min-w-0 flex-1 overflow-y-auto p-2">
                  <Command.Empty className="px-3 py-8 text-center text-small text-ink-muted">
                    Nothing matches. Try a page name or “copy”.
                  </Command.Empty>
                  {PALETTE_GROUPS.map((group) => (
                    <Command.Group
                      key={group}
                      heading={group}
                      className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:label-instrument"
                    >
                      {PALETTE_ITEMS.filter((item) => item.group === group).map((item) => (
                        <Command.Item
                          key={item.id}
                          value={item.id}
                          keywords={[item.label, ...item.keywords]}
                          onSelect={() => run(item)}
                          className="flex h-10 cursor-pointer items-center gap-2.5 rounded-control px-2 text-[14px] text-ink-muted data-[selected=true]:bg-surface data-[selected=true]:text-ink"
                        >
                          <item.icon aria-hidden="true" className="size-4 shrink-0" />
                          <span className="truncate">{item.label}</span>
                          {/* The detail pane is visual only; its text reaches assistive tech here. */}
                          <span className="sr-only">
                            . {item.detail} {item.token}
                          </span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  ))}
                </Command.List>
                <DetailPane item={selected} />
              </div>
              <div className="flex h-9 items-center gap-4 border-t border-line px-4 text-[12px] text-ink-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↑</Kbd>
                  <Kbd>↓</Kbd> navigate
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↵</Kbd> run
                </span>
              </div>
            </Command>
          </motion.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
