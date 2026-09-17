/**
 * The Runs filter bar. Every control writes to the same `RunsSearch` object the
 * URL holds, so a filtered view is always a link. The component itself does no
 * navigating — the page owns that — which keeps it testable without a router.
 */
import { Search, SlidersHorizontal, X } from 'lucide-react'
import { Dialog } from 'radix-ui'
import { useEffect, useState } from 'react'

import { SegmentedControl } from '@/components/primitives/SegmentedControl'
import { cn } from '@/lib/utils'

import { FAULT_TYPES, type FaultType, type RunOutcome, type RunStatus } from './api'
import type { RunFacets } from './runRows'
import { type RunsSearch, clearFilters, hasActiveFilters } from './runsSearch'

const SEARCH_DEBOUNCE_MS = 200

const ALL = 'all'
type WithAll<T extends string> = T | typeof ALL

const OUTCOME_OPTIONS = [
  { value: ALL, label: 'All' },
  { value: 'pass', label: '✓ Pass' },
  { value: 'fail', label: '✕ Fail' },
] as const

const STATUS_OPTIONS = [
  { value: ALL, label: 'All' },
  { value: 'complete', label: 'Complete' },
  { value: 'recording', label: 'Recording' },
] as const

const FAULT_LABELS: Readonly<Record<FaultType, string>> = {
  wrong_value: 'wrong value',
  missing_field: 'missing field',
  stale_record: 'stale record',
  tool_error: 'tool error',
}

function fromAll<T extends string>(value: WithAll<T>): T | null {
  return value === ALL ? null : value
}

interface ChipGroupProps<T extends string> {
  readonly label: string
  readonly options: readonly { readonly value: T; readonly label: string }[]
  readonly value: T | null
  readonly onChange: (value: T | null) => void
}

/** Single-select chips; pressing the active chip clears the filter. */
function ChipGroup<T extends string>({ label, options, value, onChange }: ChipGroupProps<T>) {
  if (options.length === 0) return null
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 label-instrument">{label}_</span>
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(active ? null : option.value)}
            className={cn(
              'inline-flex h-7 cursor-pointer items-center rounded-pill border px-2.5 text-small whitespace-nowrap',
              active
                ? 'border-ink-muted bg-elevated font-medium text-ink'
                : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

interface SearchFieldProps {
  readonly value: string
  readonly onChange: (value: string) => void
}

function SearchField({ value, onChange }: SearchFieldProps) {
  const [draft, setDraft] = useState(value)
  const [lastValue, setLastValue] = useState(value)

  // The URL wins when it changes underneath us (back button, cleared filters).
  if (lastValue !== value) {
    setLastValue(value)
    setDraft(value)
  }

  useEffect(() => {
    if (draft === value) return undefined
    const timer = window.setTimeout(() => onChange(draft), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, value, onChange])

  return (
    <div className="relative flex h-9 min-w-0 flex-1 items-center gap-2 rounded-control border border-line bg-surface px-2.5 sm:max-w-72">
      <Search aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
      <input
        type="search"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="Search run or task id"
        aria-label="Search runs by run id or task id"
        className="h-full min-w-0 flex-1 bg-transparent text-small text-ink outline-none placeholder:text-ink-muted"
      />
    </div>
  )
}

interface FilterControlsProps {
  readonly search: RunsSearch
  readonly facets: RunFacets
  readonly onChange: (next: RunsSearch) => void
}

function FilterControls({ search, facets, onChange }: FilterControlsProps) {
  return (
    <>
      <SegmentedControl
        label="Filter by outcome"
        options={OUTCOME_OPTIONS}
        value={(search.outcome ?? ALL) as WithAll<RunOutcome>}
        onChange={(value) => onChange({ ...search, outcome: fromAll(value) })}
      />
      <SegmentedControl
        label="Filter by status"
        options={STATUS_OPTIONS}
        value={(search.status ?? ALL) as WithAll<RunStatus>}
        onChange={(value) => onChange({ ...search, status: fromAll(value) })}
      />
      <ChipGroup
        label="domain"
        options={facets.domains.map((domain) => ({ value: domain, label: domain }))}
        value={search.domain}
        onChange={(domain) => onChange({ ...search, domain })}
      />
      <ChipGroup
        label="fault"
        options={FAULT_TYPES.map((fault) => ({ value: fault, label: FAULT_LABELS[fault] }))}
        value={search.fault}
        onChange={(fault) => onChange({ ...search, fault })}
      />
      <ChipGroup
        label="model"
        options={facets.models.map((model) => ({
          value: model,
          label: model.split('/').at(-1) ?? model,
        }))}
        value={search.model}
        onChange={(model) => onChange({ ...search, model })}
      />
    </>
  )
}

interface RunsFiltersProps {
  readonly search: RunsSearch
  readonly facets: RunFacets
  readonly onChange: (next: RunsSearch) => void
  /** The result count, shown beside the controls. */
  readonly summary: string
}

export function RunsFilters({ search, facets, onChange, summary }: RunsFiltersProps) {
  const [sheetOpen, setSheetOpen] = useState(false)
  const active = hasActiveFilters(search)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <SearchField value={search.q} onChange={(q) => onChange({ ...search, q })} />

        {/* At 390 the controls move into a sheet rather than wrapping into five rows. */}
        <Dialog.Root open={sheetOpen} onOpenChange={setSheetOpen}>
          <Dialog.Trigger asChild>
            <button
              type="button"
              className="inline-flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-control border border-line-strong bg-elevated px-3 text-small font-medium text-ink md:hidden"
            >
              <SlidersHorizontal aria-hidden="true" className="size-3.5" />
              Filters
              {active ? <span className="size-1.5 rounded-full bg-measure" /> : null}
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-(--z-overlay) bg-(--bx-scrim) backdrop-blur-sm" />
            <Dialog.Content className="fixed inset-x-0 bottom-0 z-(--z-palette) max-h-[85vh] overflow-y-auto rounded-t-modal border-t border-line-strong bg-elevated p-5">
              <div className="mb-4 flex items-center justify-between">
                <Dialog.Title className="text-h2 text-ink">Filters</Dialog.Title>
                <Dialog.Close asChild>
                  <button
                    type="button"
                    aria-label="Close filters"
                    className="inline-flex size-8 cursor-pointer items-center justify-center rounded-control border border-line text-ink-muted"
                  >
                    <X aria-hidden="true" className="size-4" />
                  </button>
                </Dialog.Close>
              </div>
              <Dialog.Description className="sr-only">
                Narrow the run list. Every choice is kept in the page address.
              </Dialog.Description>
              <div className="flex flex-col items-start gap-4">
                <FilterControls search={search} facets={facets} onChange={onChange} />
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>

      <div className="hidden flex-wrap items-center gap-x-4 gap-y-2 md:flex">
        <FilterControls search={search} facets={facets} onChange={onChange} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <output className="num text-small text-ink-muted">{summary}</output>
        {active ? (
          <button
            type="button"
            onClick={() => onChange(clearFilters(search))}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-pill border border-line px-2.5 text-small text-ink-muted hover:border-line-strong hover:text-ink"
          >
            <X aria-hidden="true" className="size-3" />
            Clear filters
          </button>
        ) : null}
      </div>
    </div>
  )
}
