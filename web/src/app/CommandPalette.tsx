import { useNavigate } from '@tanstack/react-router'
import { Command, defaultFilter } from 'cmdk'
import { Filter, Radio, Search, Voicemail } from 'lucide-react'
import { motion } from 'motion/react'
import { Dialog } from 'radix-ui'
import { useState } from 'react'

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
import { RunPreview } from './RunPreview'

const DETAIL_FADE_SECONDS = 0.1

const GROUP_HEADING =
  '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:label-instrument'
const ITEM_ROW =
  'flex h-10 cursor-pointer items-center gap-2.5 rounded-control px-2 text-[14px] text-ink-muted data-[selected=true]:bg-surface data-[selected=true]:text-ink'

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
  /** Set for run results: the pane then shows the run itself, not a sentence about it. */
  readonly runId?: string
}

function paletteDetail(item: PaletteItem): DetailContent {
  return { ...item, group: item.group }
}

function runDetail(hit: SearchHit): DetailContent {
  const recording = hit.status === 'recording'
  return {
    id: `run:${hit.id}`,
    icon: recording ? Radio : Voicemail,
    group: 'Runs',
    label: hit.title,
    detail: recording
      ? `${hit.subtitle ?? 'A recorded run'} — still recording, so it has no outcome yet.`
      : (hit.subtitle ?? 'A recorded run.'),
    token: hit.href,
    runId: hit.id,
  }
}

const FILTER_RUNS_ID = 'action:filter-runs'

function filterRunsDetail(query: string): DetailContent {
  return {
    id: FILTER_RUNS_ID,
    icon: Filter,
    group: 'Actions',
    label: `Filter Runs by “${query}”`,
    detail:
      'Opens the Runs table with this text as its filter, so every match is listed, sortable and shareable by URL.',
    token: `/runs?q=${encodeURIComponent(query)}`,
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
      className="hidden w-72 shrink-0 flex-col gap-3 border-l border-line p-4 md:flex"
    >
      <span className="inline-flex size-10 items-center justify-center rounded-kpi border border-line-strong bg-surface text-ink">
        <Icon className="size-5" />
      </span>
      <div className="flex flex-col gap-1">
        <span className="label-instrument">{item.group}_</span>
        <span className="text-h3 text-ink">{item.label}</span>
      </div>
      <p className="text-small text-pretty text-ink-muted">{item.detail}</p>
      {item.runId ? <RunPreview runId={item.runId} /> : null}
      <code className="rounded-control border border-line bg-ground px-2 py-1.5 font-mono text-small break-all text-ink">
        {item.token}
      </code>
    </motion.aside>
  )
}

/** A run from `/api/search`. Recording runs carry their own glyph, never an outcome. */
function RunHitItem({ hit, onRun }: { readonly hit: SearchHit; readonly onRun: () => void }) {
  const recording = hit.status === 'recording'
  // A recorded run is a tape; one still being recorded is live.
  const Icon = recording ? Radio : Voicemail
  return (
    <Command.Item
      value={`run:${hit.id}`}
      keywords={[hit.title, hit.subtitle ?? '']}
      onSelect={onRun}
      className={ITEM_ROW}
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

function selectionStillListed(
  selectedId: string,
  query: string,
  hits: readonly SearchHit[],
): boolean {
  if (selectedId === '') return false
  if (selectedId === FILTER_RUNS_ID) return true
  if (hits.some((hit) => `run:${hit.id}` === selectedId)) return true
  const item = PALETTE_ITEMS.find((candidate) => candidate.id === selectedId)
  if (!item) return false
  return query.trim() === '' || defaultFilter(item.id, query, [item.label, ...item.keywords]) > 0
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

  // The previous selection is usually gone once the results change, so it is
  // dropped during render (not in an effect) and cmdk selects the new first row.
  const [lastQuery, setLastQuery] = useState(debouncedQuery)
  if (lastQuery !== debouncedQuery) {
    setLastQuery(debouncedQuery)
    setSelectedId('')
  }

  // A selection can outlive its row: Enter inside the debounce window would otherwise
  // run an item cmdk has already filtered out. Then the search falls back to its one
  // guaranteed row, or to the first run once hits arrive.
  const firstHit = hits[0]
  const fallbackId = firstHit ? `run:${firstHit.id}` : FILTER_RUNS_ID
  const activeId =
    selectionStillListed(selectedId, query, hits) || !searching ? selectedId : fallbackId
  const selectedHit = hits.find((hit) => `run:${hit.id}` === activeId)
  const selectedItem = PALETTE_ITEMS.find((item) => item.id === activeId)
  const trimmedQuery = query.trim()
  const selected = selectedHit
    ? runDetail(selectedHit)
    : selectedItem
      ? paletteDetail(selectedItem)
      : activeId === FILTER_RUNS_ID
        ? filterRunsDetail(trimmedQuery)
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
              value={activeId}
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
                {/* 8px pad + 34px heading + nine 40px rows + 8px pad: results never end mid-row. */}
                <Command.List className="max-h-[min(410px,56vh)] min-w-0 flex-1 scroll-pb-10 overflow-y-auto p-2">
                  <Command.Empty className="px-3 py-8 text-center text-small text-ink-muted">
                    Nothing matches. Try a run id, a page name or “copy”.
                  </Command.Empty>
                  {searching ? (
                    <Command.Group heading="Runs" className={GROUP_HEADING}>
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
                    <Command.Group key={group} heading={group} className={GROUP_HEADING}>
                      {PALETTE_ITEMS.filter((item) => item.group === group).map((item) => (
                        <Command.Item
                          key={item.id}
                          value={item.id}
                          keywords={[item.label, ...item.keywords]}
                          onSelect={() => run(item)}
                          className={ITEM_ROW}
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
                  {/* Last, so a page or command that matches the text still wins Enter. */}
                  {searching ? (
                    <Command.Group heading="Actions" forceMount className={GROUP_HEADING}>
                      <Command.Item
                        value={FILTER_RUNS_ID}
                        // Always offered while searching: cmdk must not filter it against the query.
                        forceMount
                        onSelect={() => {
                          onOpenChange(false)
                          void navigate({ to: '/runs', search: { q: trimmedQuery } })
                        }}
                        className={ITEM_ROW}
                      >
                        <Filter aria-hidden="true" className="size-4 shrink-0" />
                        <span className="truncate">Filter Runs by “{trimmedQuery}”</span>
                      </Command.Item>
                    </Command.Group>
                  ) : null}
                  {/* Bottom fade: the list dissolves instead of being sliced by the footer. */}
                  <div
                    aria-hidden="true"
                    className="pointer-events-none sticky bottom-0 -mb-2 h-8 bg-linear-to-t from-elevated to-transparent"
                  />
                </Command.List>
                <DetailPane item={selected} />
              </div>
              <div className="flex h-9 items-center gap-4 border-t border-line px-4 text-[12px] text-ink-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↑</Kbd>
                  <Kbd>↓</Kbd> navigate
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↵</Kbd> open
                </span>
              </div>
            </Command>
          </motion.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
