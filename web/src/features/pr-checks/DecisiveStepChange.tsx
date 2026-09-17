import { ArrowRight } from 'lucide-react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { cn } from '@/lib/utils'

import type { PrCheckDetail } from './api'

interface StepChipProps {
  readonly step: number | null
  readonly blamed: boolean
}

/** Amber is blame and only blame: the head's decisive step wears it, the base's does not. */
function StepChip({ step, blamed }: StepChipProps) {
  if (step === null) {
    return (
      <span className="inline-flex h-11 items-center rounded-step border border-dashed border-line-strong px-3 num text-small text-ink-muted">
        none
      </span>
    )
  }
  return (
    <span
      className={cn(
        'inline-flex h-11 items-center gap-1.5 rounded-step border px-3 num text-h3 font-semibold',
        blamed
          ? 'border-blame/50 bg-blame-tint text-blame'
          : 'border-line-strong bg-elevated text-ink',
      )}
    >
      <span className="label-instrument">step</span>
      {step}
    </span>
  )
}

function verdict(check: PrCheckDetail): string {
  const { decisive_step_base: base, decisive_step_head: head } = check
  if (base === null && head === null) return 'No step was decisive on either ref.'
  if (base === null) return 'Head has a decisive step where base had none.'
  if (head === null) return 'Base had a decisive step; head has none.'
  if (base === head) return 'The same step is decisive on both refs.'
  return 'The decisive step moved between the two refs.'
}

interface DecisiveStepChangeProps {
  readonly check: PrCheckDetail
}

/**
 * Which step the blame rule lands on, on each ref.
 *
 * The per-step revert effect and its interval are not in this payload — the
 * gate reports them in its comment — so this panel shows what it has and says
 * where the rest lives, rather than parsing a number out of prose.
 */
export function DecisiveStepChange({ check }: DecisiveStepChangeProps) {
  const moved =
    check.decisive_step_base !== check.decisive_step_head && check.decisive_step_head !== null
  const neither = check.decisive_step_base === null && check.decisive_step_head === null

  // Nothing was decisive on either ref: one line, not half a page of chrome
  // explaining the absence of a result.
  if (neither) {
    return (
      <Panel variant="elevated" bodyClassName="flex flex-col gap-1">
        <InstrumentLabel>decisive_step</InstrumentLabel>
        <p className="text-h3 text-ink">No step was decisive on either ref.</p>
      </Panel>
    )
  }

  return (
    <Panel variant="elevated" bodyClassName="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <InstrumentLabel>decisive_step</InstrumentLabel>
        <h3 className="text-h3 text-ink">Where the blame rule lands</h3>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <span className="flex flex-col gap-1">
          <span className="label-instrument">base</span>
          <StepChip step={check.decisive_step_base} blamed={false} />
        </span>
        <ArrowRight aria-hidden="true" className="mt-5 size-4 shrink-0 text-ink-muted" />
        <span className="flex flex-col gap-1">
          <span className="label-instrument">head</span>
          <StepChip step={check.decisive_step_head} blamed={check.is_regression} />
        </span>
        <span
          className={cn(
            'mt-5 rounded-pill border px-2 py-0.5 text-[12px] whitespace-nowrap',
            // "moved" describes a change, not a blamed step, so it stays neutral.
            moved ? 'border-line-strong bg-elevated text-ink' : 'border-line-strong text-ink-muted',
          )}
        >
          {moved ? 'moved' : 'unchanged'}
        </span>
      </div>

      <p className="max-w-prose text-small text-pretty text-ink-muted">{verdict(check)}</p>
      <InstrumentLabel>effect not returned here · see the comment below</InstrumentLabel>
    </Panel>
  )
}
