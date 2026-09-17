import { cn } from '@/lib/utils'

interface StepSparklineProps {
  /** One value per step, in step order. */
  readonly values: readonly number[]
  /** What the values are, for the accessible name: "tokens per step". */
  readonly label: string
  /** 0-based index to mark (the blamed step). */
  readonly markIndex?: number
  readonly width?: number
  readonly height?: number
  readonly className?: string
}

const DEFAULT_WIDTH = 96
const DEFAULT_HEIGHT = 24
const PADDING = 3
const MARK_RADIUS = 2.5

interface Point {
  readonly x: number
  readonly y: number
}

function toPoints(values: readonly number[], width: number, height: number): readonly Point[] {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const stepX = values.length > 1 ? (width - PADDING * 2) / (values.length - 1) : 0
  return values.map((value, index) => ({
    x: PADDING + index * stepX,
    y: height - PADDING - ((value - min) / span) * (height - PADDING * 2),
  }))
}

/** Row-sized trace of a per-step quantity. Pure SVG so a virtualized table stays cheap. */
export function StepSparkline({
  values,
  label,
  markIndex,
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
  className,
}: StepSparklineProps) {
  if (values.length === 0) {
    return <span className={cn('num text-small text-ink-muted', className)}>no steps</span>
  }
  const points = toPoints(values, width, height)
  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`)
    .join(' ')
  const mark = markIndex === undefined ? undefined : points[markIndex]
  const summary = `${label}: ${values.length} steps, min ${Math.min(...values)}, max ${Math.max(...values)}`
  return (
    <svg
      role="img"
      aria-label={mark ? `${summary}, step ${(markIndex ?? 0) + 1} marked` : summary}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn('shrink-0', className)}
    >
      <path
        d={path}
        fill="none"
        stroke="var(--bx-muted)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {mark ? (
        <circle
          cx={mark.x}
          cy={mark.y}
          r={MARK_RADIUS}
          fill="var(--bx-blame)"
          stroke="var(--bx-surface)"
        />
      ) : null}
    </svg>
  )
}
