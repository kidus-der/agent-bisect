/**
 * Illustrative, deterministic datasets for the /gallery chart demos: hand-picked
 * values or fixed formulas, nothing measured. Rows are `type` aliases (not
 * interfaces) so a copy is assignable to the `Record<string, unknown>` rows Bklit expects.
 */
import type { RoleName } from '@/design/tokens'

/** recall@m: share of failures whose true culprit is in a method's top-m blamed steps. */
export type RecallAtMRow = {
  readonly m: number
  readonly replay: number
  readonly judge: number
}

export const RECALL_AT_M: readonly RecallAtMRow[] = [
  { m: 1, replay: 62, judge: 41 },
  { m: 2, replay: 78, judge: 55 },
  { m: 3, replay: 86, judge: 64 },
  { m: 4, replay: 91, judge: 70 },
  { m: 5, replay: 94, judge: 74 },
]

export type PassRateRow = {
  readonly date: Date
  readonly treated: number
  readonly control: number
}

const TREATED_PASS_RATES = [58, 61, 60, 66, 69, 68, 72, 74, 73, 77, 76, 79, 80, 81] as const
const CONTROL_PASS_RATES = [31, 33, 30, 34, 32, 35, 33, 36, 34, 35, 37, 34, 36, 36] as const
const NIGHTLY_START = { year: 2026, monthIndex: 7, day: 1 } as const

function nightlyDate(offsetDays: number): Date {
  return new Date(NIGHTLY_START.year, NIGHTLY_START.monthIndex, NIGHTLY_START.day + offsetDays)
}

/** Pass rate (%) of N re-runs per nightly benchmark: intervention applied vs replayed as recorded. */
export const PASS_RATE_BY_NIGHT: readonly PassRateRow[] = TREATED_PASS_RATES.map(
  (treated, index) => ({
    date: nightlyDate(index),
    treated,
    control: CONTROL_PASS_RATES[index] ?? 0,
  }),
)

export type CostBinRow = {
  /** Upper edge of the bin, in US cents per bisected run. */
  readonly bin: string
  readonly runs: number
}

export const COST_PER_RUN_BINS: readonly CostBinRow[] = [
  { bin: '5¢', runs: 6 },
  { bin: '10¢', runs: 19 },
  { bin: '15¢', runs: 34 },
  { bin: '20¢', runs: 27 },
  { bin: '25¢', runs: 15 },
  { bin: '30¢', runs: 9 },
  { bin: '35¢', runs: 4 },
  { bin: '40¢+', runs: 2 },
]

export type CostByNightRow = {
  readonly date: Date
  readonly replay: number
  readonly judge: number
}

const REPLAY_COST_CENTS = [21, 19, 23, 18, 20, 17, 19, 16, 18, 15, 17, 16, 14, 15] as const
const JUDGE_COST_CENTS = [6, 7, 6, 8, 7, 7, 9, 8, 7, 8, 9, 8, 9, 8] as const

/** Mean cost (US cents) of localising one failure, per nightly benchmark and method. */
export const COST_BY_NIGHT: readonly CostByNightRow[] = REPLAY_COST_CENTS.map((replay, index) => ({
  date: nightlyDate(index),
  replay,
  judge: JUDGE_COST_CENTS[index] ?? 0,
}))

export type CalendarDay = { readonly date: Date; readonly count: number }
export type CalendarWeek = { readonly week: number; readonly days: readonly CalendarDay[] }

const CALENDAR_WEEKS = 18
const DAYS_PER_WEEK = 7
/** Sunday 3 May 2026, so day index 0 lines up with the chart's Sunday-first rows. */
const CALENDAR_START = { year: 2026, monthIndex: 4, day: 3 } as const

function bisectionsOn(week: number, day: number): number {
  const isWeekend = day === 0 || day === DAYS_PER_WEEK - 1
  if (isWeekend || (week + day) % 6 === 0) return 0
  return 1 + ((week * 5 + day * 3) % 4)
}

/** Bisections run per day. The Bklit heatmap buckets counts as 0, 1, 2, 3 and 4+. */
export const BISECTIONS_PER_DAY: readonly CalendarWeek[] = Array.from(
  { length: CALENDAR_WEEKS },
  (_, week) => ({
    week,
    days: Array.from({ length: DAYS_PER_WEEK }, (_unused, day) => ({
      date: new Date(
        CALENDAR_START.year,
        CALENDAR_START.monthIndex,
        CALENDAR_START.day + week * DAYS_PER_WEEK + day,
      ),
      count: bisectionsOn(week, day),
    })),
  }),
)

/** Provider rate limit: calls made in the current minute, of the 40 req/min cap. */
export const RATE_LIMIT_BUDGET = { used: 27, limit: 40 } as const

export type SpendRing = {
  readonly label: string
  readonly spentUsd: number
  readonly capUsd: number
  readonly role: RoleName
}

/** Today's spend against each stage's daily cap. */
export const DAILY_SPEND: readonly SpendRing[] = [
  { label: 'replay', spentUsd: 3.2, capUsd: 5, role: 'measure' },
  { label: 'llm judge', spentUsd: 1.1, capUsd: 2, role: 'judge' },
  { label: 'recording', spentUsd: 0.3, capUsd: 1, role: 'tape' },
]

export type AgreementMetric = { readonly key: string; readonly label: string }
export type AgreementSeries = {
  readonly label: string
  readonly role: RoleName
  readonly values: Readonly<Record<string, number>>
}

export const AGREEMENT_METRICS: readonly AgreementMetric[] = [
  { key: 'precision', label: 'precision' },
  { key: 'recall', label: 'recall' },
  { key: 'agreement', label: 'agreement' },
  { key: 'kappa', label: 'κ' },
  { key: 'coverage', label: 'coverage' },
]

/** Each method scored against human-labelled culprit steps, all on a 0–100 scale. */
export const AGREEMENT_SERIES: readonly AgreementSeries[] = [
  {
    label: 'replay',
    role: 'measure',
    values: { precision: 88, recall: 81, agreement: 84, kappa: 71, coverage: 92 },
  },
  {
    label: 'llm judge',
    role: 'judge',
    values: { precision: 64, recall: 58, agreement: 66, kappa: 43, coverage: 100 },
  },
]

export type FunnelStep = { readonly label: string; readonly value: number }

/** Labels stay one short word: the funnel gives each a nowrap column 16% of the chart wide. */
export const BISECT_FUNNEL: readonly FunnelStep[] = [
  { label: 'recorded', value: 1240 },
  { label: 'failed', value: 412 },
  { label: 'bisected', value: 310 },
  { label: 'blamed', value: 236 },
  { label: 'confirmed', value: 188 },
]

export type OutcomeNode = {
  readonly name: string
  readonly category: 'source' | 'outcome'
  readonly role: RoleName
}
export type OutcomeLink = {
  readonly source: number
  readonly target: number
  readonly value: number
}

/** Where each method's top-1 blame landed, 120 labelled failures per method. */
export const OUTCOME_NODES: readonly OutcomeNode[] = [
  { name: 'replay', category: 'source', role: 'measure' },
  { name: 'llm judge', category: 'source', role: 'judge' },
  { name: 'correct step', category: 'outcome', role: 'pass' },
  { name: 'off-by-one', category: 'outcome', role: 'tape' },
  { name: 'wrong step', category: 'outcome', role: 'fail' },
  { name: 'abstained', category: 'outcome', role: 'tape' },
]

export const OUTCOME_LINKS: readonly OutcomeLink[] = [
  { source: 0, target: 2, value: 79 },
  { source: 0, target: 3, value: 19 },
  { source: 0, target: 4, value: 12 },
  { source: 0, target: 5, value: 10 },
  { source: 1, target: 2, value: 49 },
  { source: 1, target: 3, value: 27 },
  { source: 1, target: 4, value: 44 },
]

/** Calls per second over the last half minute, oldest first. Replayed against the clock by the live demo. */
export const CALLS_PER_SECOND_LOOP: readonly number[] = [
  3, 4, 4, 6, 5, 7, 9, 8, 6, 5, 4, 6, 8, 11, 9, 7, 6, 5, 7, 8, 10, 12, 9, 7, 5, 4, 6, 7, 9, 8,
]
