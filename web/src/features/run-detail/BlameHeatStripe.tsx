import { useId } from 'react'

import { formatEffect } from '@/lib/format'

import type { HeatCell } from './blame'
import { heatBucket } from './heatScale'
import type { TimelineGeometry } from './timelineScale'

const HATCH_SIZE = 5
const CELL_RADIUS = 2

interface BlameHeatStripeProps {
  readonly cells: readonly HeatCell[]
  readonly geometry: TimelineGeometry
  readonly blamedStep: number | null
  readonly height: number
  readonly onHoverStep?: (step: number | null) => void
}

/** The blame stripe, aligned cell-for-cell under the tape. Untested steps are hatched. */
export function BlameHeatStripe({
  cells,
  geometry,
  blamedStep,
  height,
  onHoverStep,
}: BlameHeatStripeProps) {
  const uid = useId()
  const hatchId = `${uid}-hatch`
  const blameId = `${uid}-blame`
  return (
    <svg
      aria-hidden="true"
      width={geometry.contentWidth}
      height={height}
      viewBox={`0 0 ${geometry.contentWidth} ${height}`}
      onPointerLeave={() => onHoverStep?.(null)}
      className="block"
    >
      <defs>
        <pattern
          id={hatchId}
          width={HATCH_SIZE}
          height={HATCH_SIZE}
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <line x1={0} y1={0} x2={0} y2={HATCH_SIZE} stroke="var(--bx-tape)" strokeWidth={1.5} />
        </pattern>
        <linearGradient id={blameId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--bx-blame)" />
          <stop offset="1" stopColor="var(--bx-blame-coral)" />
        </linearGradient>
      </defs>
      {cells.map((cell) => {
        const blamed = cell.tested && cell.step === blamedStep
        const fill = !cell.tested
          ? `url(#${hatchId})`
          : blamed
            ? `url(#${blameId})`
            : heatBucket(cell.effect ?? 0)
        return (
          <rect
            key={cell.step}
            data-state={cell.tested ? (blamed ? 'blamed' : 'tested') : 'untested'}
            data-step={cell.step}
            x={geometry.x(cell.step)}
            y={0.5}
            width={geometry.bandWidth}
            height={height - 1}
            rx={CELL_RADIUS}
            fill={fill}
            stroke={blamed ? 'var(--bx-blame)' : 'var(--bx-line-strong)'}
            onPointerEnter={() => onHoverStep?.(cell.step)}
          >
            <title>
              {cell.tested
                ? `Step ${cell.step}: effect ${formatEffect(cell.effect ?? 0)}`
                : `Step ${cell.step}: not tested`}
            </title>
          </rect>
        )
      })}
    </svg>
  )
}
