import { motion, useReducedMotion } from 'motion/react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { NotMeasuredState } from '@/components/primitives/NotMeasuredState'
import { Panel } from '@/components/primitives/Panel'
import { springTransition } from '@/design/motion'
import { formatPercent, formatPoints } from '@/lib/stats'
import { cn } from '@/lib/utils'

import { MAX_RATE, ratePercent, rateSpanPercent } from './accuracyScale'
import type { CiValue, FlakyAblation as FlakyAblationPayload } from './api'

const ARM_COPY = {
  snapshot: {
    label: 'With snapshots',
    caption: 'World state restored from the tape before each re-run.',
    fill: 'var(--bx-measure)',
  },
  no_snapshot: {
    label: 'Without snapshots',
    caption: 'Re-runs inherit whatever state the previous run left behind.',
    fill: 'var(--bx-tape)',
  },
} as const

interface ArmRowProps {
  readonly name: keyof typeof ARM_COPY
  readonly accuracy: CiValue
  readonly index: number
}

function ArmRow({ name, accuracy, index }: ArmRowProps) {
  const reduced = useReducedMotion() ?? false
  const copy = ARM_COPY[name]
  const { value, ci_low: low, ci_high: high } = accuracy
  const enter = {
    ...springTransition('settle', reduced),
    delay: reduced ? 0 : index * 0.08,
  }
  return (
    <li className="flex flex-col gap-2 border-t border-line pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-h3 font-semibold text-ink">{copy.label}</span>
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
          transition={enter}
          style={{ width: ratePercent(value, MAX_RATE), background: copy.fill, originX: 0 }}
          className="absolute top-1/2 left-0 h-2.5 -translate-y-1/2 rounded-r-step"
        />
        <span
          style={{
            left: ratePercent(low, MAX_RATE),
            width: rateSpanPercent(low, high, MAX_RATE),
          }}
          className="absolute top-1/2 h-px -translate-y-1/2 bg-ink"
        />
        {[low, high].map((bound) => (
          <span
            key={bound}
            style={{ left: ratePercent(bound, MAX_RATE) }}
            className="absolute top-1/2 -ml-px h-3 w-px -translate-y-1/2 bg-ink"
          />
        ))}
      </div>
      <p className="text-[12px] text-ink-muted">{copy.caption}</p>
    </li>
  )
}

interface FlakyAblationProps {
  /** Null when the evaluation has no no-snapshot arm. */
  readonly ablation: FlakyAblationPayload | null
}

/**
 * The ablation that justifies the snapshot engine (brief §2): under a flaky
 * world, does restoring state actually buy accuracy? The difference and its
 * interval are the answer, so the difference is the hero — not either arm.
 */
export function FlakyAblation({ ablation }: FlakyAblationProps) {
  // No flaky-world run, no comparison. The panel stays and says so rather than
  // vanishing: a missing ablation is a fact about the evaluation, not an
  // absence of UI.
  if (ablation === null) {
    return (
      <Panel variant="elevated">
        <NotMeasuredState
          label="flaky_world_ablation"
          title="No flaky-world run to compare against"
          reason="This evaluation has no no-snapshot arm, so what snapshots are worth was not measured."
          command="bisect bench --flaky-world"
        />
      </Panel>
    )
  }
  const { difference } = ablation
  const decisive = difference.ci_low > 0
  return (
    <Panel
      variant="elevated"
      bodyClassName="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]"
    >
      <div className="flex flex-col gap-3">
        <InstrumentLabel>flaky_world_ablation</InstrumentLabel>
        <h3 className="text-h2 text-ink">What snapshots are worth</h3>
        <div className="flex flex-col gap-1">
          <span className="num text-display font-semibold text-measure">
            {formatPoints(difference.value)}
          </span>
          <span className="num text-small text-ink-muted">
            95% CI [{formatPoints(difference.ci_low)}, {formatPoints(difference.ci_high)}]
          </span>
        </div>
        <span
          className={cn(
            'inline-flex w-fit items-center gap-1.5 rounded-pill border px-2.5 py-1 text-small font-medium',
            decisive
              ? 'border-measure/40 bg-measure-tint text-measure'
              : 'border-line-strong bg-elevated text-ink-muted',
          )}
        >
          <span aria-hidden="true">{decisive ? '✓' : '·'}</span>
          {decisive ? 'interval excludes zero' : 'interval includes zero'}
        </span>
        <p className="max-w-prose text-small text-pretty text-ink-muted">
          Plain τ² tools are deterministic, so snapshots there only buy speed. In the flaky world —
          generated ids, a moving clock, occasional tool errors — they are what keeps a replay
          honest. This is the gap they close.
        </p>
      </div>

      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {ablation.arms.map((arm, index) => (
          <ArmRow key={arm.name} name={arm.name} accuracy={arm.accuracy} index={index} />
        ))}
      </ul>
    </Panel>
  )
}
