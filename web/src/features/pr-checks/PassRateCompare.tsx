import { motion, useReducedMotion } from 'motion/react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { springTransition } from '@/design/motion'
import { formatPValue, formatPercent, formatPoints, newcombeInterval } from '@/lib/stats'
import { cn } from '@/lib/utils'

import type { CiValue, PrCheckDetail } from './api'

const MAX_RATE = 1
const PERCENT = 100

function percent(rate: number): string {
  return `${(Math.min(1, Math.max(0, rate)) / MAX_RATE) * PERCENT}%`
}

function spanPercent(low: number, high: number): string {
  return `${Math.max(0, Math.min(1, high) - Math.min(1, low)) * PERCENT}%`
}

interface RefRowProps {
  readonly ref: 'base' | 'head'
  readonly rate: CiValue
  readonly index: number
  readonly regressed: boolean
  /** False when the difference's interval crosses zero: nothing was shown. */
  readonly decisive: boolean
}

function RefRow({ ref: refName, rate, index, regressed, decisive }: RefRowProps) {
  const reduced = useReducedMotion() ?? false
  const head = refName === 'head'
  // Base is the quiet reference. Head only takes a semantic colour when the
  // difference is decisive — otherwise the panel would say "better" and "not
  // significant" at the same time.
  const fill =
    !head || !decisive ? 'var(--bx-tape)' : regressed ? 'var(--bx-fail)' : 'var(--bx-pass)'
  const { value, ci_low: low, ci_high: high } = rate
  return (
    <li className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="flex items-baseline gap-2">
          <InstrumentLabel>{refName}</InstrumentLabel>
          {head ? (
            <span className="text-[12px] text-ink-muted">this pull request</span>
          ) : (
            <span className="text-[12px] text-ink-muted">the branch it merges into</span>
          )}
        </span>
        <span className="num text-h2 text-ink">
          {formatPercent(value)}{' '}
          <span className="num text-[12px] text-ink-muted">
            [{formatPercent(low)}, {formatPercent(high)}]
          </span>
        </span>
      </div>
      <div aria-hidden="true" className="relative h-4">
        <motion.span
          initial={reduced ? undefined : { scaleX: 0 }}
          whileInView={reduced ? undefined : { scaleX: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{
            ...springTransition('settle', reduced),
            delay: reduced ? 0 : index * 0.08,
          }}
          style={{ width: percent(value), background: fill, originX: 0 }}
          className="absolute top-1/2 left-0 h-2.5 -translate-y-1/2 rounded-r-step"
        />
        <span
          style={{ left: percent(low), width: spanPercent(low, high) }}
          className="absolute top-1/2 h-px -translate-y-1/2 bg-ink"
        />
        {[low, high].map((bound) => (
          <span
            key={bound}
            style={{ left: percent(bound) }}
            className="absolute top-1/2 -ml-px h-3 w-px -translate-y-1/2 bg-ink"
          />
        ))}
      </div>
    </li>
  )
}

interface PassRateCompareProps {
  readonly check: PrCheckDetail
}

/** Focal element of a PR check: the verdict, then base against head with intervals. */
export function PassRateCompare({ check }: PassRateCompareProps) {
  const regressed = check.is_regression
  const runs = check.scenarios.reduce((sum, scenario) => sum + scenario.n, 0)
  const difference = newcombeInterval(
    check.head_pass_rate.value,
    runs,
    check.base_pass_rate.value,
    runs,
  )
  const decisive = difference !== null && (difference.low > 0 || difference.high < 0)

  return (
    <Panel variant="canvas" bodyClassName="grid gap-6 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
      <div className="flex flex-col gap-3">
        <InstrumentLabel>gate_verdict</InstrumentLabel>
        <span
          className={cn(
            'inline-flex w-fit items-center gap-2 rounded-pill border px-3 py-1.5 text-h3 font-semibold',
            regressed
              ? 'border-fail/40 bg-fail-tint text-fail'
              : 'border-pass/40 bg-pass-tint text-pass',
          )}
        >
          <span aria-hidden="true">{regressed ? '✕' : '✓'}</span>
          {regressed ? 'Regression detected' : 'No regression'}
        </span>
        <div className="flex flex-col gap-1">
          <span
            className={cn(
              'num text-display font-semibold',
              regressed && decisive ? 'text-fail' : 'text-ink',
            )}
          >
            {formatPoints(check.head_pass_rate.value - check.base_pass_rate.value)}
          </span>
          <span className="num text-small text-ink-muted">
            {difference
              ? `95% CI [${formatPoints(difference.low)}, ${formatPoints(difference.high)}]`
              : 'interval not computable'}
          </span>
        </div>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
          <dt className="label-instrument">p value</dt>
          <dd className="m-0 num text-small text-ink">{formatPValue(check.p_value)}</dd>
          <dt className="label-instrument">suite</dt>
          <dd className="m-0 num text-small text-ink">
            {check.scenarios.length} scenarios · {runs} runs
          </dd>
        </dl>
        <p className="max-w-prose text-[12px] text-pretty text-ink-muted">
          Head minus base on the same scenario suite, with a Newcombe 95% interval over {runs} runs
          per ref. The p value is the server's two-proportion test.
        </p>
      </div>

      <ul className="m-0 flex list-none flex-col justify-center gap-6 p-0">
        <RefRow
          ref="base"
          rate={check.base_pass_rate}
          index={0}
          regressed={regressed}
          decisive={decisive}
        />
        <RefRow
          ref="head"
          rate={check.head_pass_rate}
          index={1}
          regressed={regressed}
          decisive={decisive}
        />
      </ul>
    </Panel>
  )
}
