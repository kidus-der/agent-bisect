/**
 * The feed's information density.
 *
 * The server emits one line per progress tick, all shaped
 * `simulated: <phase> batch <id> progressed`, so eight rows carried about one
 * row of information. Consecutive ticks for the same batch collapse into one
 * entry that counts them and keeps the newest timestamp; anything the parser
 * does not recognise is passed through untouched, because a message it has not
 * seen before is exactly the one worth reading in full.
 */
import type { LiveEvent } from './liveBuffer'

/** `simulated: blame batch 29827852 progressed`. */
const BATCH_PATTERN = /^(simulated:\s*)?(\w+)\s+batch\s+(\S+)\s*(.*)$/

export interface EventGroup {
  /** Stable across re-renders for the same batch and level. */
  readonly key: string
  readonly ts: string
  readonly level: LiveEvent['level']
  readonly simulated: boolean
  /** `blame`, `eval`, `record` — null when the message is not a batch tick. */
  readonly phase: string | null
  readonly batch: string | null
  readonly detail: string
  /** How many consecutive ticks this entry stands for. */
  readonly count: number
}

interface Parsed {
  readonly simulated: boolean
  readonly phase: string | null
  readonly batch: string | null
  readonly detail: string
}

export function parseEvent(message: string): Parsed {
  const match = BATCH_PATTERN.exec(message.trim())
  if (!match) return { simulated: false, phase: null, batch: null, detail: message }
  return {
    simulated: Boolean(match[1]),
    phase: match[2] ?? null,
    batch: match[3] ?? null,
    detail: (match[4] ?? '').trim() || 'progressed',
  }
}

/** Collapses consecutive ticks for one batch. Order is preserved (newest first). */
export function groupEvents(events: readonly LiveEvent[]): readonly EventGroup[] {
  return events.reduce<EventGroup[]>((groups, event) => {
    const parsed = parseEvent(event.message)
    const previous = groups[groups.length - 1]
    const sameBatch =
      previous !== undefined &&
      parsed.batch !== null &&
      previous.batch === parsed.batch &&
      previous.level === event.level &&
      previous.detail === parsed.detail
    if (sameBatch && previous) {
      return [...groups.slice(0, -1), { ...previous, count: previous.count + 1 }]
    }
    return [
      ...groups,
      {
        key: `${event.ts}-${parsed.batch ?? event.message}-${event.level}`,
        ts: event.ts,
        level: event.level,
        simulated: parsed.simulated,
        phase: parsed.phase,
        batch: parsed.batch,
        detail: parsed.detail,
        count: 1,
      },
    ]
  }, [])
}

const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE

/** `now`, `12s ago`, `4m ago` — how old a line is, against the clock in the header. */
export function formatAge(ts: string, now: number): string {
  const parsed = Date.parse(ts)
  if (!Number.isFinite(parsed)) return '—'
  const age = Math.max(0, now - parsed)
  if (age < 5 * SECOND) return 'now'
  if (age < MINUTE) return `${Math.round(age / SECOND)}s ago`
  if (age < HOUR) return `${Math.round(age / MINUTE)}m ago`
  return `${Math.round(age / HOUR)}h ago`
}
