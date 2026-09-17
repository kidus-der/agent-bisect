import { useId } from 'react'

import { formatEffect } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface HeatStep {
  /** 1-based step index. */
  readonly step: number
  /** Effect estimate, or null when the step was never tested. */
  readonly effect: number | null
}

interface HeatStripeProps {
  readonly steps: readonly HeatStep[]
  /** 1-based index of the blamed step, if any. */
  readonly blamedStep?: number
  readonly cellWidth?: number
  readonly cellHeight?: number
  /** Show `#7 +0.75` after the stripe. Blame never appears without its number. */
  readonly showBlameCaption?: boolean
  readonly className?: string
}

const DEFAULT_CELL_WIDTH = 14
const DEFAULT_CELL_HEIGHT = 16
const CELL_GAP = 2
const CELL_RADIUS = 2
const SCALE_STEPS = 5
const HATCH_SIZE = 5

/** Effect in [0, 1] -> one of the five sequential scale variables. Never guesses for null. */
function scaleVariable(effect: number): string {
  const clamped = Math.min(1, Math.max(0, effect))
  const bucket = Math.min(SCALE_STEPS, Math.floor(clamped * SCALE_STEPS) + 1)
  return `var(--chart-scale-0${bucket})`
}

function describe(steps: readonly HeatStep[], blamedStep: number | undefined): string {
  const tested = steps.filter((entry) => entry.effect !== null)
  const untested = steps.length - tested.length
  const strongest = tested.reduce<HeatStep | undefined>(
    (best, entry) => ((entry.effect ?? 0) > (best?.effect ?? -Infinity) ? entry : best),
    undefined,
  )
  const parts = [
    `Effect per step: ${steps.length} steps, ${tested.length} tested, ${untested} untested (hatched).`,
  ]
  if (strongest && strongest.effect !== null) {
    parts.push(`Largest effect ${formatEffect(strongest.effect)} at step ${strongest.step}.`)
  }
  if (blamedStep !== undefined) parts.push(`Blamed step: ${blamedStep}.`)
  return parts.join(' ')
}

/** Effect per step. Untested steps are hatched, never given a guessed colour. */
export function HeatStripe({
  steps,
  blamedStep,
  cellWidth = DEFAULT_CELL_WIDTH,
  cellHeight = DEFAULT_CELL_HEIGHT,
  showBlameCaption = true,
  className,
}: HeatStripeProps) {
  const uid = useId()
  const hatchId = `${uid}-hatch`
  const blameId = `${uid}-blame`
  const width = steps.length * (cellWidth + CELL_GAP) - CELL_GAP
  const blamed = steps.find((entry) => entry.step === blamedStep)

  return (
    <span data-slot="heat-stripe" className={cn('inline-flex items-center gap-2', className)}>
      <svg
        role="img"
        aria-label={describe(steps, blamedStep)}
        width={Math.max(width, 0)}
        height={cellHeight}
        viewBox={`0 0 ${Math.max(width, 0)} ${cellHeight}`}
        className="shrink-0"
      >
        <defs>
          <pattern
            id={hatchId}
            width={HATCH_SIZE}
            height={HATCH_SIZE}
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1={0} y1={0} x2={0} y2={HATCH_SIZE} stroke="var(--bx-tape)" strokeWidth={2} />
          </pattern>
          <linearGradient id={blameId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--bx-blame)" />
            <stop offset="1" stopColor="var(--bx-blame-coral)" />
          </linearGradient>
        </defs>
        {steps.map((entry, index) => {
          const isBlamed = entry.step === blamedStep && entry.effect !== null
          const fill =
            entry.effect === null
              ? `url(#${hatchId})`
              : isBlamed
                ? `url(#${blameId})`
                : scaleVariable(entry.effect)
          return (
            <rect
              key={entry.step}
              data-state={entry.effect === null ? 'untested' : isBlamed ? 'blamed' : 'tested'}
              x={index * (cellWidth + CELL_GAP) + 0.5}
              y={0.5}
              width={cellWidth - 1}
              height={cellHeight - 1}
              rx={CELL_RADIUS}
              fill={fill}
              stroke={isBlamed ? 'var(--bx-blame)' : 'var(--bx-line-strong)'}
            >
              <title>
                {entry.effect === null
                  ? `Step ${entry.step}: not tested`
                  : `Step ${entry.step}: effect ${formatEffect(entry.effect)}`}
              </title>
            </rect>
          )
        })}
      </svg>
      {showBlameCaption && blamed && blamed.effect !== null ? (
        <span
          aria-hidden="true"
          className="num text-[11px] font-medium whitespace-nowrap text-blame"
        >
          #{blamed.step} {formatEffect(blamed.effect)}
        </span>
      ) : null}
    </span>
  )
}
