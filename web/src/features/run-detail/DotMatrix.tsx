import { Link } from '@tanstack/react-router'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Check, X } from 'lucide-react'
import { useRef, memo } from 'react'

import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

import type { RerunRow } from './api'
import { BATCH_SIZE, type RerunGroup, groupReruns } from './rerunGroups'

const ROW_HEIGHT = 34
/** Below this the label, the dots and the count cannot share one line. */
const STACKED_ROW_HEIGHT = 52
const WIDE_QUERY = '(min-width: 640px)'
const OVERSCAN = 6
const MAX_VISIBLE_ROWS = 11
/** A dot stays a legible target while the grid fills the panel. */
const DOT_MAX_PX = 26

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
        'flex aspect-square w-full items-center justify-center rounded-[3px] border',
        row.passed
          ? 'border-pass/50 bg-pass-tint text-pass'
          : 'border-fail/50 bg-fail-tint text-fail',
      )}
    >
      <Glyph aria-hidden="true" className="size-3" strokeWidth={3} />
    </Link>
  )
}

interface MatrixRowProps {
  readonly group: RerunGroup
  readonly runId: string
  readonly selected: boolean
  /** Columns in the shared grid: the widest arm, so every row aligns. */
  readonly columns: number
  readonly wide: boolean
  readonly onSelectStep: (step: number) => void
}

function MatrixRow({ group, runId, selected, columns, wide, onSelectStep }: MatrixRowProps) {
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

  const label = (
    <button
      type="button"
      onClick={() => onSelectStep(group.step)}
      className="shrink-0 cursor-pointer text-left num text-small whitespace-nowrap text-ink-muted hover:text-ink sm:w-32"
    >
      {group.arm === 'control' ? (
        <span>control{group.shared ? ' · shared' : ` · k=${group.step}`}</span>
      ) : (
        <span className="text-ink">step {group.step}</span>
      )}
    </button>
  )
  // The count reads immediately after the last cell, not pinned to a far edge.
  const count = (
    <span className="shrink-0 num text-small whitespace-nowrap text-ink-muted">
      {group.passed}/{group.rows.length}
    </span>
  )

  return (
    <div
      ref={rowRef}
      className={cn(
        'rounded-step px-1',
        wide ? 'flex items-center gap-4' : 'flex flex-col justify-center gap-1 py-1',
        selected && 'bg-elevated ring-1 ring-line-strong',
      )}
      style={{ height: wide ? ROW_HEIGHT : STACKED_ROW_HEIGHT }}
    >
      {wide ? (
        label
      ) : (
        <div className="flex items-baseline justify-between gap-2">
          {label}
          {count}
        </div>
      )}
      {/* One grid of `columns` equal cells on every row, so column i is the same
          batch position on every arm and no dot is clipped at 390px. */}
      <div
        className={cn('grid min-w-0 gap-1', wide ? '' : 'w-full')}
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, ${DOT_MAX_PX}px))` }}
      >
        {group.rows.map((row, index) => (
          <Dot
            key={row.rerun_id}
            row={row}
            runId={runId}
            index={index}
            total={group.rows.length}
            onKeyDown={handleKeyDown}
          />
        ))}
      </div>
      {wide ? count : null}
    </div>
  )
}

interface BatchRulerProps {
  readonly columns: number
  readonly wide: boolean
}

/**
 * Where the sequential estimator looked. The dots are one aligned grid, so the
 * batch boundaries read better as a ruler above them than as gaps between them.
 */
function BatchRuler({ columns, wide }: BatchRulerProps) {
  const looks = Array.from(
    { length: Math.floor(columns / BATCH_SIZE) },
    (_, i) => (i + 1) * BATCH_SIZE,
  )
  return (
    <div className={cn('mb-1 px-1', wide ? 'flex items-end gap-4' : '')}>
      {wide ? <span aria-hidden="true" className="w-32 shrink-0" /> : null}
      <div
        aria-hidden="true"
        className={cn('grid min-w-0 gap-1', wide ? '' : 'w-full')}
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, ${DOT_MAX_PX}px))` }}
      >
        {Array.from({ length: columns }, (_, index) => {
          const look = looks.includes(index + 1)
          return (
            <span key={index} className="flex flex-col items-center">
              <span
                className={cn('num text-[10px] leading-3', look ? 'text-ink-muted' : 'sr-only')}
              >
                {look ? index + 1 : ''}
              </span>
              <span className={cn('h-1 w-px', look ? 'bg-line-strong' : 'bg-transparent')} />
            </span>
          )
        })}
      </div>
      <span className="sr-only">Batch boundaries every {BATCH_SIZE} re-runs.</span>
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
function DotMatrixImpl({ rows, runId, selectedStep, onSelectStep }: DotMatrixProps) {
  // TanStack Virtual returns fresh functions each render; the compiler must not memoise them.
  'use no memo'
  const groups = groupReruns(rows)
  const wide = useMediaQuery(WIDE_QUERY)
  const rowHeight = wide ? ROW_HEIGHT : STACKED_ROW_HEIGHT
  // The widest arm sets the grid, so a short arm ends early instead of stretching.
  const columns = groups.reduce((widest, group) => Math.max(widest, group.rows.length), 1)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const virtualizer = useVirtualizer({
    count: groups.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
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
      <BatchRuler columns={columns} wide={wide} />
      <div
        ref={scrollRef}
        className="overflow-y-auto"
        style={{ maxHeight: rowHeight * MAX_VISIBLE_ROWS }}
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
                  columns={columns}
                  wide={wide}
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

/**
 * Memoised: a rewind tick re-renders the page several times a second, and none
 * of this panel's inputs change while the tape is replaying.
 */
export const DotMatrix = memo(DotMatrixImpl)
