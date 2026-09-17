import { Panel } from '@/components/primitives/Panel'
import { cn } from '@/lib/utils'

import { type EventGroup, formatAge, groupEvents } from './eventGroups'
import type { LiveEvent } from './liveBuffer'
import { EVENT_BUFFER_LIMIT } from './liveBuffer'

/**
 * Colour on this feed is spent on `error` alone. A warning is raised by its `!`
 * glyph and its tag, not by amber: amber means blame and nothing else
 * (direction.md §3, principle 2).
 */
const LEVEL_STYLES: Readonly<Record<LiveEvent['level'], { glyph: string; className: string }>> = {
  info: { glyph: '·', className: 'text-ink-muted' },
  warn: { glyph: '!', className: 'text-ink' },
  error: { glyph: '✕', className: 'text-fail' },
}

/** Local wall-clock, to the second: the feed is read against what is happening now. */
function formatTime(ts: string): string {
  const parsed = Date.parse(ts)
  if (!Number.isFinite(parsed)) return '--:--:--'
  return new Date(parsed).toLocaleTimeString('en-GB', { hour12: false })
}

function GroupRow({ group, now }: { readonly group: EventGroup; readonly now: number }) {
  const level = LEVEL_STYLES[group.level]
  return (
    <li className="grid grid-cols-[auto_auto_minmax(0,1fr)_auto] items-baseline gap-x-3 border-b border-line py-2 last:border-b-0">
      <span className="num text-[12px] text-ink-muted">{formatTime(group.ts)}</span>
      <span className="flex items-baseline gap-1.5">
        <span className={cn('label-instrument whitespace-nowrap', level.className)}>
          <span aria-hidden="true">{level.glyph}</span> {group.level}
        </span>
        {group.phase ? (
          <span className="rounded-step border border-line-strong bg-elevated px-1 label-instrument text-ink">
            {group.phase}
          </span>
        ) : null}
      </span>
      <span className="min-w-0 text-small text-pretty text-ink">
        {group.batch ? (
          <>
            <span className="num text-ink-muted">batch {group.batch}</span> {group.detail}
          </>
        ) : (
          group.detail
        )}
        {/* One entry can stand for several ticks; saying how many keeps it honest. */}
        {group.count > 1 ? (
          <span className="num text-[12px] text-ink-muted"> ×{group.count}</span>
        ) : null}
      </span>
      <span className="text-right num text-[12px] whitespace-nowrap text-ink-muted">
        {formatAge(group.ts, now)}
      </span>
    </li>
  )
}

interface EventFeedProps {
  readonly events: readonly LiveEvent[]
  /** The clock the ages are measured against; passed in so it is not read per row. */
  readonly now: number
}

/**
 * Newest first, capped at the ring's length, consecutive ticks for one batch
 * collapsed. Announced politely: a feed that interrupts a screen-reader user
 * every two seconds is unusable, so only new lines are announced.
 */
export function EventFeed({ events, now }: EventFeedProps) {
  const groups = groupEvents(events)
  return (
    <Panel
      variant="card"
      label="events"
      title="Recent events"
      actions={
        <span className="num text-small text-ink-muted">
          newest first · last {EVENT_BUFFER_LIMIT}
        </span>
      }
    >
      {groups.length === 0 ? (
        <p className="py-6 text-ink-muted">No events yet on this connection.</p>
      ) : (
        // A scrollable region must be reachable by keyboard and needs a name once
        // it is (WCAG 2.1.1, axe `scrollable-region-focusable`). jsx-a11y objects
        // to tabIndex on a non-interactive role; WCAG wins, and the focus sits on
        // a wrapper — as in DataTable — so the list keeps its list semantics.
        <div
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- WCAG 2.1.1 wins
          tabIndex={0}
          role="group"
          aria-label="Recent events, newest first"
          className="max-h-72 overflow-y-auto -outline-offset-2"
        >
          <ol
            aria-live="polite"
            aria-relevant="additions"
            className="m-0 flex list-none flex-col p-0"
          >
            {groups.map((group) => (
              <GroupRow key={group.key} group={group} now={now} />
            ))}
          </ol>
        </div>
      )}
    </Panel>
  )
}
