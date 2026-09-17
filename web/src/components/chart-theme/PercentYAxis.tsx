/**
 * The y-axis shared by every chart whose value is a rate: a gridline plus a
 * right-aligned tabular label per tick, in the chart theme's own colours.
 *
 * Ticks are given as proportions in [0, 1] and labelled as whole percentages,
 * so a chart never has to decide how to render its own axis numbers.
 */
import { chartColours } from './chartTheme'

const LABEL_GAP_PX = 10
const LABEL_FONT_PX = 11
/** Centres the label on its gridline across fonts. */
const BASELINE_SHIFT = '0.32em'

interface PercentYAxisProps {
  /** Proportions in [0, 1], in any order. */
  readonly ticks: readonly number[]
  /** The chart's y scale: a proportion in, a pixel offset out. */
  readonly scale: (value: number) => number
  /** Plot width, so each gridline spans it. */
  readonly width: number
  /** Axis title, drawn rotated to the left of the labels. */
  readonly title?: string
  /** Height of the plot area, used to centre the title. */
  readonly height?: number
  /** Distance from the plot's left edge to the title. */
  readonly titleOffset?: number
}

export function PercentYAxis({
  ticks,
  scale,
  width,
  title,
  height = 0,
  titleOffset = 32,
}: PercentYAxisProps) {
  return (
    <g aria-hidden="true">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={0} x2={width} y1={scale(tick)} y2={scale(tick)} stroke={chartColours.grid} />
          <text
            x={-LABEL_GAP_PX}
            y={scale(tick)}
            dy={BASELINE_SHIFT}
            textAnchor="end"
            fontSize={LABEL_FONT_PX}
            fill={chartColours.label}
            className="num"
          >
            {Math.round(tick * 100)}
          </text>
        </g>
      ))}
      {title ? (
        <text
          transform={`translate(${-titleOffset} ${height / 2}) rotate(-90)`}
          textAnchor="middle"
          fontSize={LABEL_FONT_PX}
          fill={chartColours.label}
        >
          {title}
        </text>
      ) : null}
    </g>
  )
}
