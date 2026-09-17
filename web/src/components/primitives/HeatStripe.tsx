import { useId } from 'react'

import { formatEffect } from '@/lib/format'
import { cn } from '@/lib/utils'

import { buildHeatScale, bucketVariable } from './heatScale'

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
  /**
   * Total width the stripe fills, divided by the step count. Prefer this in a
   * table: it keeps step *position* comparable down a column, where a constant
   * cell width makes a 27-step stripe a different length from an 11-step one.
   */
  readonly trackWidth?: number
  readonly cellHeight?: number
  /** Show `#7 +0.75` after the stripe. Blame never appears without its number. */
  readonly showBlameCaption?: boolean
  readonly className?: string
}

const DEFAULT_CELL_WIDTH = 14
const DEFAULT_CELL_HEIGHT = 16
const CELL_GAP = 2
const CELL_RADIUS = 2
const HATCH_SIZE = 5
/** Below this a cell is a hairline; the gap is dropped so the marks stay readable. */
const MIN_GAPPED_CELL_PX = 3

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
  trackWidth,
  cellHeight = DEFAULT_CELL_HEIGHT,
  showBlameCaption = true,
  className,
}: HeatStripeProps) {
  const uid = useId()
  const hatchId = `${uid}-hatch`
  const blameId = `${uid}-blame`
  const count = Math.max(steps.length, 1)
  // A fixed track divides exactly, so step 1 and step n land at the same x on
  // every row regardless of how many steps the run has.
  const pitch = trackWidth === undefined ? cellWidth + CELL_GAP : trackWidth / count
  const gap = pitch >= MIN_GAPPED_CELL_PX + CELL_GAP ? CELL_GAP : 0
  const drawnCellWidth = Math.max(pitch - gap, 1)
  const width = trackWidth ?? count * pitch - CELL_GAP
  const scale = buildHeatScale(steps, blamedStep)
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
          {/* The blamed cell is a fill: vivid amber to coral in both themes. */}
          <linearGradient id={blameId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--bx-blame-fill)" />
            <stop offset="1" stopColor="var(--bx-blame-coral-fill)" />
          </linearGradient>
        </defs>
        {steps.map((entry, index) => {
          const isBlamed = entry.step === blamedStep && entry.effect !== null
          const fill =
            entry.effect === null
              ? `url(#${hatchId})`
              : isBlamed
                ? `url(#${blameId})`
                : bucketVariable(scale.bucket(entry.effect))
          return (
            <rect
              key={entry.step}
              data-state={entry.effect === null ? 'untested' : isBlamed ? 'blamed' : 'tested'}
              x={index * pitch + 0.5}
              y={0.5}
              width={Math.max(drawnCellWidth - 1, 0.5)}
              height={cellHeight - 1}
              rx={CELL_RADIUS}
              fill={fill}
              stroke={isBlamed ? 'var(--bx-blame-fill)' : 'var(--bx-line-strong)'}
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
