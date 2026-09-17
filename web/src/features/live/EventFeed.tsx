import { Panel } from '@/components/primitives/Panel'
import { cn } from '@/lib/utils'

import type { LiveEvent } from './liveBuffer'
import { EVENT_BUFFER_LIMIT } from './liveBuffer'

const LEVEL_STYLES: Readonly<Record<LiveEvent['level'], { glyph: string; className: string }>> = {
  info: { glyph: '·', className: 'text-ink-muted' },
  warn: { glyph: '!', className: 'text-blame' },
  error: { glyph: '✕', className: 'text-fail' },
}

/** Local wall-clock, to the second: the feed is read against what is happening now. */
function formatTime(ts: string): string {
  const parsed = Date.parse(ts)
  if (!Number.isFinite(parsed)) return '--:--:--'
  return new Date(parsed).toLocaleTimeString('en-GB', { hour12: false })
}

interface EventFeedProps {
  readonly events: readonly LiveEvent[]
}

/**
 * Newest first, capped at the ring's length. Announced politely: a feed that
 * interrupts a screen-reader user every two seconds is unusable, so only the
 * arrival of new lines is announced, not the whole list.
 */
export function EventFeed({ events }: EventFeedProps) {
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
      {events.length === 0 ? (
        <p className="py-6 text-ink-muted">No events yet on this connection.</p>
      ) : (
        <ol
          aria-live="polite"
          aria-relevant="additions"
          className="m-0 flex max-h-72 list-none flex-col overflow-y-auto p-0"
        >
          {events.map((event) => {
            const level = LEVEL_STYLES[event.level]
            return (
              <li
                key={`${event.ts}-${event.message}`}
                className="flex items-baseline gap-3 border-b border-line py-2 last:border-b-0"
              >
                <span className="shrink-0 num text-[12px] text-ink-muted">
                  {formatTime(event.ts)}
                </span>
                <span
                  className={cn(
                    'w-14 shrink-0 label-instrument whitespace-nowrap',
                    level.className,
                  )}
                >
                  <span aria-hidden="true">{level.glyph}</span> {event.level}
                </span>
                <span className="min-w-0 text-small text-pretty text-ink">{event.message}</span>
              </li>
            )
          })}
        </ol>
      )}
    </Panel>
  )
}
