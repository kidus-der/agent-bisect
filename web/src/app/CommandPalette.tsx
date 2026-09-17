import { useNavigate } from '@tanstack/react-router'
import { Command } from 'cmdk'
import { Radio, Search, Tag } from 'lucide-react'
import { motion } from 'motion/react'
import { Dialog } from 'radix-ui'
import { useEffect, useState } from 'react'

import {
  MIN_SEARCH_CHARS,
  SEARCH_DEBOUNCE_MS,
  type SearchHit,
  runHits,
  useSearchQuery,
} from '@/api/search'
import { Kbd } from '@/components/primitives/Kbd'
import { useSpringTransition } from '@/design/motion'
import { toggleTheme } from '@/design/theme'
import { useDebouncedValue } from '@/lib/useDebouncedValue'
import { copyText } from '@/lib/useCopy'
import { cn } from '@/lib/utils'

import { PALETTE_GROUPS, PALETTE_ITEMS, type PaletteItem } from './paletteItems'

const DETAIL_FADE_SECONDS = 0.1

interface CommandPaletteProps {
  readonly open: boolean
  readonly onOpenChange: (open: boolean) => void
}

/** What the preview pane shows, whichever kind of result is selected. */
interface DetailContent {
  readonly id: string
  readonly icon: PaletteItem['icon']
  readonly group: string
  readonly label: string
  readonly detail: string
  readonly token: string
}

function paletteDetail(item: PaletteItem): DetailContent {
  return { ...item, group: item.group }
}

function runDetail(hit: SearchHit): DetailContent {
  const recording = hit.status === 'recording'
  return {
    id: `run:${hit.id}`,
    icon: recording ? Radio : Tag,
    group: 'Runs',
    label: hit.title,
    detail: recording
      ? `${hit.subtitle ?? 'A recorded run'} — still recording, so it has no outcome yet.`
      : (hit.subtitle ?? 'A recorded run.'),
    token: hit.href,
  }
}

function DetailPane({ item }: { readonly item: DetailContent | undefined }) {
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

/** A run from `/api/search`. Recording runs carry their own glyph, never an outcome. */
function RunHitItem({ hit, onRun }: { readonly hit: SearchHit; readonly onRun: () => void }) {
  const recording = hit.status === 'recording'
  const Icon = recording ? Radio : Tag
  return (
    <Command.Item
      value={`run:${hit.id}`}
      keywords={[hit.title, hit.subtitle ?? '']}
      onSelect={onRun}
      className="flex h-10 cursor-pointer items-center gap-2.5 rounded-control px-2 text-[14px] text-ink-muted data-[selected=true]:bg-surface data-[selected=true]:text-ink"
    >
      <Icon aria-hidden="true" className={cn('size-4 shrink-0', recording && 'text-measure')} />
      <span className="truncate num">{hit.title}</span>
      {hit.subtitle ? (
        <span className="truncate text-[12px] text-ink-muted">{hit.subtitle}</span>
      ) : null}
      {recording ? <span className="ml-auto shrink-0 label-instrument">recording</span> : null}
    </Command.Item>
  )
}

/** ⌘K. Raycast layout: filter input, result list, detail preview. Filtering is instant. */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const transition = useSpringTransition('snap')
  const [selectedId, setSelectedId] = useState<string>(PALETTE_ITEMS[0]?.id ?? '')
  const [query, setQuery] = useState('')

  // Runs come from the server; the static items above are filtered by cmdk.
  const debouncedQuery = useDebouncedValue(query, SEARCH_DEBOUNCE_MS)
  const search = useSearchQuery(debouncedQuery)
  const hits = runHits(search.data?.data)
  const searching = query.trim().length >= MIN_SEARCH_CHARS

  // The previous selection is usually gone once the list changes; clearing it
  // lets cmdk select the new first row and report it back.
  useEffect(() => setSelectedId(''), [debouncedQuery])

  const selectedHit = hits.find((hit) => `run:${hit.id}` === selectedId)
  const selectedItem = PALETTE_ITEMS.find((item) => item.id === selectedId)
  const selected = selectedHit
    ? runDetail(selectedHit)
    : selectedItem
      ? paletteDetail(selectedItem)
      : undefined

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
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Search runs, jump to a page, or run a command"
                  className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-muted"
                />
                <Kbd>esc</Kbd>
              </div>
              <div className="flex min-h-0">
                <Command.List className="max-h-[min(420px,56vh)] min-w-0 flex-1 overflow-y-auto p-2">
                  <Command.Empty className="px-3 py-8 text-center text-small text-ink-muted">
                    Nothing matches. Try a run id, a page name or “copy”.
                  </Command.Empty>
                  {searching ? (
                    <Command.Group
                      heading="Runs"
                      className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:label-instrument"
                    >
                      {hits.length === 0 ? (
                        <p className="px-2 py-1.5 text-small text-ink-muted">
                          {search.isPending ? 'Searching…' : 'No run matches.'}
                        </p>
                      ) : (
                        hits.map((hit) => (
                          <RunHitItem
                            key={hit.id}
                            hit={hit}
                            onRun={() => {
                              onOpenChange(false)
                              void navigate({ to: hit.href })
                            }}
                          />
                        ))
                      )}
                    </Command.Group>
                  ) : null}
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
