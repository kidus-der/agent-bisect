/**
 * The Runs table. Sorting is the server's (the header only reflects and
 * requests it), rows are virtualized, and below the md breakpoint each row
 * becomes a two-line card instead of a sideways scroll.
 */
import { ChevronRight } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

import { DataTable, type DataTableColumn } from '@/components/primitives/DataTable'
import type { SortState } from '@/components/primitives/dataTableSort'
import { layoutIds, useSpringTransition } from '@/design/motion'
import { useMediaQuery } from '@/lib/useMediaQuery'

import type { RunSummary, SortableRunField } from './api'
import { RunBlame, RunBlameStripe, RunNumber, RunOutcome, RunSparkline } from './cells'
import type { RunsSearch } from './runsSearch'

const ROW_HEIGHT = 46
const COMPACT_ROW_HEIGHT = 92
const MIN_TABLE_HEIGHT = 320
const DEFAULT_TABLE_HEIGHT = 560
/** Room below the table: the panel edge, plus the bottom tab bar where it exists. */
const BOTTOM_GUTTER_PX = { wide: 48, narrow: 96 } as const
const WIDE_QUERY = '(min-width: 768px)'

/** Column ids double as the API's sort keys, so a header click maps straight through. */
const SORTABLE: ReadonlySet<string> = new Set<SortableRunField>([
  'run_id',
  'domain',
  'n_steps',
  'outcome',
  'cost_usd',
  'calls',
])

/**
 * Measured rather than guessed: how much page is above the table depends on how
 * many rows of filter chips wrapped, which differs at every width.
 */
function useTableHeight(ref: React.RefObject<HTMLElement | null>, gutter: number): number {
  const [height, setHeight] = useState(DEFAULT_TABLE_HEIGHT)
  useEffect(() => {
    const update = (): void => {
      const top = ref.current?.getBoundingClientRect().top ?? 0
      setHeight(Math.max(MIN_TABLE_HEIGHT, window.innerHeight - top - gutter))
    }
    update()
    window.addEventListener('resize', update)
    // The filter chips only get their real height once the facets load, which
    // moves the table down without any resize event firing.
    const observer = new ResizeObserver(update)
    observer.observe(document.body)
    return () => {
      window.removeEventListener('resize', update)
      observer.disconnect()
    }
  }, [ref, gutter])
  return height
}

const ROW_SELECTOR = 'tr[tabindex], li[tabindex]'

/**
 * Up and down move between rows; Enter and Space are the DataTable's own. The
 * listener is delegated to the container imperatively: the wrapper is not itself
 * interactive, the rows are.
 */
function useRowArrowKeys(ref: React.RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const container = ref.current
    if (!container) return undefined
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
      const rows = [...container.querySelectorAll<HTMLElement>(ROW_SELECTOR)]
      const index = rows.indexOf(document.activeElement as HTMLElement)
      if (index === -1) return
      const next = rows[index + (event.key === 'ArrowDown' ? 1 : -1)]
      if (!next) return
      event.preventDefault()
      next.focus()
    }
    container.addEventListener('keydown', onKeyDown)
    return () => container.removeEventListener('keydown', onKeyDown)
  }, [ref])
}

/**
 * The chip the Run detail header morphs from (signature moment §7.4).
 *
 * `inline-block` is load-bearing: a plain `<span>` is `display: inline`, and CSS
 * transforms do not apply to non-replaced inline boxes — the shared-layout
 * animation ran and moved nothing. Under reduced motion the id carries no
 * `layoutId` at all, so the two pages swap instantly.
 */
function RunIdChip({ runId }: { readonly runId: string }) {
  const reduced = useReducedMotion() ?? false
  const transition = useSpringTransition('glide')
  if (reduced) return <span className="num font-medium text-ink">{runId}</span>
  return (
    <motion.span
      layoutId={layoutIds.runRow(runId)}
      transition={transition}
      className="inline-block num font-medium text-ink"
    >
      {runId}
    </motion.span>
  )
}

const RUN_COLUMNS: ReadonlyArray<DataTableColumn<RunSummary>> = [
  {
    id: 'run_id',
    header: 'Run',
    width: '15rem',
    cell: (run) => <RunIdChip runId={run.run_id} />,
    sortValue: (run) => run.run_id,
  },
  {
    id: 'task',
    header: 'Task',
    cell: (run) => <span className="text-ink-muted">{run.task_id}</span>,
  },
  {
    id: 'domain',
    header: 'Domain',
    width: '7rem',
    cell: (run) => <span className="text-ink-muted">{run.domain}</span>,
    sortValue: (run) => run.domain,
  },
  {
    id: 'n_steps',
    header: 'Steps',
    numeric: true,
    width: '5rem',
    cell: (run) => run.n_steps,
    sortValue: (run) => run.n_steps,
  },
  {
    id: 'spark',
    header: 'Shape',
    width: '7rem',
    cell: (run) => <RunSparkline run={run} />,
  },
  {
    id: 'blame_stripe',
    header: 'Effect per step',
    width: '10rem',
    cell: (run) => <RunBlameStripe run={run} />,
  },
  {
    id: 'decisive',
    header: 'Decisive',
    width: '11rem',
    cell: (run) => <RunBlame run={run} />,
  },
  {
    id: 'outcome',
    header: 'Outcome',
    width: '8rem',
    cell: (run) => <RunOutcome run={run} />,
    sortValue: (run) => run.outcome,
  },
  {
    id: 'cost_usd',
    header: 'Cost',
    numeric: true,
    width: '6rem',
    cell: (run) => <RunNumber value={run.cost_usd} decimals={2} prefix="$" />,
    sortValue: (run) => run.cost_usd,
  },
  {
    id: 'calls',
    header: 'Calls',
    numeric: true,
    width: '6rem',
    cell: (run) => <RunNumber value={run.calls} />,
    sortValue: (run) => run.calls,
  },
  {
    // The blueprint ends each row in an affordance; rows are clickable and
    // nothing else said so.
    id: 'open',
    header: '',
    width: '2.5rem',
    cell: () => (
      <ChevronRight
        aria-hidden="true"
        className="size-4 text-ink-muted transition-colors group-hover/row:text-ink"
      />
    ),
  },
]

function CompactRun({ run }: { readonly run: RunSummary }) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <RunIdChip runId={run.run_id} />
        <RunOutcome run={run} />
      </div>
      <p className="truncate text-small text-ink-muted">
        {run.task_id} · {run.domain} · <span className="num">{run.n_steps}</span> steps
      </p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <RunBlameStripe run={run} />
        <RunBlame run={run} />
        <RunNumber
          value={run.cost_usd}
          decimals={2}
          prefix="$"
          className="text-small text-ink-muted"
        />
      </div>
    </>
  )
}

interface RunsTableProps {
  readonly rows: readonly RunSummary[]
  readonly search: RunsSearch
  readonly onSortChange: (column: SortableRunField) => void
  readonly onOpen: (run: RunSummary) => void
  /** Warms the run's detail data on hover or focus, before any click. */
  readonly onIntent: (run: RunSummary) => void
  /** What the footer reports, e.g. "40 of 266 shown". */
  readonly footer: string
}

export function RunsTable({
  rows,
  search,
  onSortChange,
  onOpen,
  onIntent,
  footer,
}: RunsTableProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const wide = useMediaQuery(WIDE_QUERY)
  const height = useTableHeight(
    containerRef,
    wide ? BOTTOM_GUTTER_PX.wide : BOTTOM_GUTTER_PX.narrow,
  )
  useRowArrowKeys(containerRef)
  const sort: SortState = { columnId: search.sort, direction: search.dir }

  return (
    <div ref={containerRef}>
      <div className="relative">
        <DataTable
          columns={RUN_COLUMNS}
          rows={rows}
          getRowId={(run) => run.run_id}
          caption="Recorded runs"
          sort={sort}
          onSortChange={(columnId) => {
            if (SORTABLE.has(columnId)) onSortChange(columnId as SortableRunField)
          }}
          onRowActivate={onOpen}
          onRowIntent={onIntent}
          maxHeight={height}
          rowHeight={ROW_HEIGHT}
          compactRowHeight={COMPACT_ROW_HEIGHT}
          renderCompactRow={(run) => <CompactRun run={run} />}
        />
        {/* The list used to end sliced flat at the card edge; this says it continues. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-surface to-transparent"
        />
      </div>
      <div className="flex items-center justify-between border-t border-line px-3 py-2">
        <span className="num text-small text-ink-muted">{footer}</span>
      </div>
    </div>
  )
}
