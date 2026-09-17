import { useReducedMotion } from 'motion/react'
import { useMemo } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { roleColour } from '@/components/chart-theme/chartTheme'
import {
  SankeyChart,
  type SankeyData,
  SankeyLink,
  SankeyNode,
  SankeyTooltip,
} from '@/components/charts/sankey'

import { formatPercent } from '@/lib/stats'
import { useMediaQuery } from '@/lib/useMediaQuery'

import type { SankeyFlow } from './api'
import { buildBlameFlow, describeBlameFlow } from './blameFlow'

const ENTER_DURATION_MS = 1100
/**
 * Node labels are drawn outside the nodes, so the side margins have to hold the
 * longest label — but fixed margins leave almost no plot on a 390px screen, so
 * they scale with the available width between a readable floor and that ceiling.
 */
const MARGIN_Y = 12
const MIN_LEFT = 88
const MAX_LEFT = 104
const MIN_RIGHT = 96
const MAX_RIGHT = 118

const WIDE_MARGIN = {
  top: MARGIN_Y,
  bottom: MARGIN_Y,
  left: MAX_LEFT,
  right: MAX_RIGHT,
} as const
const NARROW_MARGIN = {
  top: MARGIN_Y,
  bottom: MARGIN_Y,
  left: MIN_LEFT,
  right: MIN_RIGHT,
} as const

const NARROW_QUERY = '(max-width: 640px)'

const NODE_WIDTH = 10
const NODE_PADDING = 16
/** A node holding 3 of 86 failures is otherwise a few pixels tall. */
const MIN_NODE_HEIGHT = 12
const LINK_OPACITY = 0.38
const FADED_OPACITY = 0.08
const NO_MOTION = { duration: 0 } as const

interface BlameFlowSankeyProps {
  readonly rows: readonly SankeyFlow[]
}

/** Planted fault type on the left, where the blame actually landed on the right. */
export function BlameFlowSankey({ rows }: BlameFlowSankeyProps) {
  const reduced = useReducedMotion() === true
  const narrow = useMediaQuery(NARROW_QUERY)
  // Short names at every width: the count appended to each label is what the
  // long name used to carry, and together they no longer fit the side margin.
  const graph = useMemo(() => buildBlameFlow(rows, true), [rows])
  const exact = rows.reduce((sum, row) => sum + (row.label === 'exact' ? row.count : 0), 0)

  // The chart's `data` prop is typed mutable and carries no role, so it gets a copy.
  const chartData: SankeyData = useMemo(
    () => ({
      nodes: graph.nodes.map((node) => ({ name: node.name, category: node.category })),
      links: graph.links.map((link) => ({ ...link })),
    }),
    [graph],
  )

  const nodeColour = (_node: unknown, index: number): string => {
    const role = graph.nodes[index]?.role
    return role ? roleColour(role) : roleColour('tape')
  }

  return (
    <ChartFrame
      variant="kpi"
      label="fault_to_blame"
      title="Where the blame landed"
      description={describeBlameFlow(rows, graph.total)}
      heightClassName="h-80"
      legend={
        <span className="shrink-0 text-right text-[12px] text-ink-muted">
          <span className="num text-h3 text-pass">
            {exact}/{graph.total}
          </span>{' '}
          exact
          <br />
          <span className="num">
            {graph.total > 0 ? formatPercent(exact / graph.total) : 'n/a'}
          </span>
        </span>
      }
    >
      <SankeyChart
        data={chartData}
        aspectRatio="auto"
        className="h-full"
        margin={narrow ? NARROW_MARGIN : WIDE_MARGIN}
        nodeWidth={NODE_WIDTH}
        nodePadding={NODE_PADDING}
        minNodeHeight={MIN_NODE_HEIGHT}
        animationDuration={reduced ? 0 : ENTER_DURATION_MS}
        enterTransition={reduced ? NO_MOTION : undefined}
      >
        <SankeyLink
          getNodeColor={nodeColour}
          strokeOpacity={LINK_OPACITY}
          fadedOpacity={FADED_OPACITY}
        />
        {/* The built-in value label hard-codes "sessions", so counts live in the tooltip. */}
        <SankeyNode getNodeColor={nodeColour} showValueLabels={false} />
        <SankeyTooltip formatValue={(value: number) => `${value} failures`} />
      </SankeyChart>
    </ChartFrame>
  )
}
