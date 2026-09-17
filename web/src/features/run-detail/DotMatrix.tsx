import { Link } from '@tanstack/react-router'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Check, X } from 'lucide-react'
import { useRef } from 'react'

import { cn } from '@/lib/utils'

import type { RerunRow } from './api'
import { BATCH_SIZE, type RerunGroup, batchesOf, groupReruns } from './rerunGroups'

const ROW_HEIGHT = 30
const OVERSCAN = 6
const MAX_VISIBLE_ROWS = 11

interface DotProps {
  readonly row: RerunRow
  readonly runId: string
  readonly index: number
  readonly total: number
  readonly onKeyDown: (event: React.KeyboardEvent<HTMLAnchorElement>) => void
}

function dotLabel({ row, index, total }: Pick<DotProps, 'row' | 'index' | 'total'>): string {
  return `Re-run ${index + 1} of ${total}, ${row.arm} step ${row.step}, seed ${row.seed}, ${
    row.passed ? 'passed' : 'failed'
  }`
}

/** One individual re-run. Outcome is glyph first, colour second. */
function Dot({ row, runId, index, total, onKeyDown }: DotProps) {
  const Glyph = row.passed ? Check : X
  return (
    <Link
      to="/runs/$runId/reruns/$rerunId"
      params={{ runId, rerunId: row.rerun_id }}
      onKeyDown={onKeyDown}
      data-dot
      data-passed={row.passed}
      tabIndex={index === 0 ? 0 : -1}
      aria-label={dotLabel({ row, index, total })}
      className={cn(
        'inline-flex size-4 shrink-0 items-center justify-center rounded-[3px] border',
        row.passed
          ? 'border-pass/50 bg-pass-tint text-pass'
          : 'border-fail/50 bg-fail-tint text-fail',
      )}
    >
      <Glyph aria-hidden="true" className="size-2.5" strokeWidth={3} />
    </Link>
  )
}

interface MatrixRowProps {
  readonly group: RerunGroup
  readonly runId: string
  readonly selected: boolean
  readonly onSelectStep: (step: number) => void
}

function MatrixRow({ group, runId, selected, onSelectStep }: MatrixRowProps) {
  const rowRef = useRef<HTMLDivElement | null>(null)

  // Roving focus: one tab stop per row, arrows walk the dots inside it.
  const handleKeyDown = (event: React.KeyboardEvent<HTMLAnchorElement>): void => {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (delta === 0) return
    const dots = rowRef.current?.querySelectorAll<HTMLElement>('[data-dot]')
    if (!dots) return
    const current = [...dots].indexOf(document.activeElement as HTMLElement)
    if (current === -1) return
    event.preventDefault()
    dots[Math.min(Math.max(current + delta, 0), dots.length - 1)]?.focus()
  }

  return (
    <div
      ref={rowRef}
      className={cn(
        'flex items-center gap-3 rounded-step px-1',
        selected && 'bg-elevated ring-1 ring-line-strong',
      )}
      style={{ height: ROW_HEIGHT }}
    >
      <button
        type="button"
        onClick={() => onSelectStep(group.step)}
        className="w-20 shrink-0 cursor-pointer truncate text-left num text-small whitespace-nowrap text-ink-muted hover:text-ink sm:w-32"
      >
        {group.arm === 'control' ? (
          <span>
            control
            {/* The qualifier is the first thing to go when the column narrows. */}
            <span className="hidden sm:inline">
              {group.shared ? ' · shared' : ` · k=${group.step}`}
            </span>
          </span>
        ) : (
          <span className="text-ink">step {group.step}</span>
        )}
      </button>
      <div className="flex min-w-0 flex-1 [scrollbar-width:none] items-center gap-x-2 overflow-x-auto [&::-webkit-scrollbar]:hidden">
        {batchesOf(group.rows, BATCH_SIZE).map((batch, batchIndex) => (
          <div key={batch[0]?.rerun_id ?? batchIndex} className="flex items-center gap-0.5">
            {batch.map((row, index) => (
              <Dot
                key={row.rerun_id}
                row={row}
                runId={runId}
                index={batchIndex * BATCH_SIZE + index}
                total={group.rows.length}
                onKeyDown={handleKeyDown}
              />
            ))}
          </div>
        ))}
      </div>
      <span className="shrink-0 num text-small whitespace-nowrap text-ink-muted">
        {group.passed}/{group.rows.length}
      </span>
    </div>
  )
}

interface DotMatrixProps {
  readonly rows: readonly RerunRow[]
  readonly runId: string
  readonly selectedStep: number
  readonly onSelectStep: (step: number) => void
}

/** Every individual re-run behind the estimate, grouped by arm and step. */
export function DotMatrix({ rows, runId, selectedStep, onSelectStep }: DotMatrixProps) {
  // TanStack Virtual returns fresh functions each render; the compiler must not memoise them.
  'use no memo'
  const groups = groupReruns(rows)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const virtualizer = useVirtualizer({
    count: groups.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  })

  if (groups.length === 0) {
    return (
      <p className="text-small text-ink-muted">
        No individual re-runs were recorded for this run, so there is nothing to show here.
      </p>
    )
  }

  return (
    <div>
      <p className="sr-only">
        {groups.length} arms, {rows.length} individual re-runs. Each dot opens that re-run.
      </p>
      <div
        ref={scrollRef}
        className="overflow-y-auto"
        style={{ maxHeight: ROW_HEIGHT * MAX_VISIBLE_ROWS }}
      >
        <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((item) => {
            const group = groups[item.index]
            if (!group) return null
            return (
              <div
                key={group.key}
                className="absolute top-0 left-0 w-full"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <MatrixRow
                  group={group}
                  runId={runId}
                  selected={group.arm === 'treated' && group.step === selectedStep}
                  onSelectStep={onSelectStep}
                />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
