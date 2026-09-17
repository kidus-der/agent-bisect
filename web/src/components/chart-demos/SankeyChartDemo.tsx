import { useReducedMotion } from 'motion/react'
import type { JSX } from 'react'

import { ChartFrame } from '@/components/chart-theme/ChartFrame'
import { chartColours, roleColour } from '@/components/chart-theme/chartTheme'
import {
  SankeyChart,
  type SankeyData,
  SankeyLink,
  SankeyNode,
  SankeyTooltip,
} from '@/components/charts/sankey'

import { OUTCOME_LINKS, OUTCOME_NODES } from './demoData'

const ENTER_DURATION_MS = 1100
/** Node labels are drawn outside the nodes, so the side margins are sized for the longest label. */
const MARGIN = { top: 12, right: 96, bottom: 12, left: 80 } as const
const NODE_WIDTH = 10
const NODE_PADDING = 18
const LINK_OPACITY = 0.35
const NO_MOTION = { duration: 0 } as const

/** Bklit's graph shape, as a copy: the chart's `data` prop is typed mutable and carries no role. */
const CHART_DATA: SankeyData = {
  nodes: OUTCOME_NODES.map((node) => ({ name: node.name, category: node.category })),
  links: OUTCOME_LINKS.map((link) => ({ ...link })),
}

function nodeColour(_node: unknown, index: number): string {
  const role = OUTCOME_NODES[index]?.role
  return role ? roleColour(role) : chartColours.control
}

function formatFailures(value: number): string {
  return `${value} failures`
}

function outcomeSummary(sourceIndex: number): string {
  const source = OUTCOME_NODES[sourceIndex]?.name ?? ''
  const parts = OUTCOME_LINKS.filter((link) => link.source === sourceIndex).map(
    (link) => `${link.value} ${OUTCOME_NODES[link.target]?.name ?? ''}`,
  )
  return `${source}: ${parts.join(', ')}`
}

export function SankeyChartDemo(): JSX.Element {
  const reduceMotion = useReducedMotion() === true
  return (
    <ChartFrame
      label="method_to_outcome"
      title="Where blame lands"
      description={`Sankey diagram of the top-1 blamed step for 120 labelled failures per method. ${outcomeSummary(0)}. ${outcomeSummary(1)}. Illustrative data.`}
      heightClassName="h-72"
    >
      <SankeyChart
        data={CHART_DATA}
        aspectRatio="auto"
        className="h-full"
        margin={MARGIN}
        nodeWidth={NODE_WIDTH}
        nodePadding={NODE_PADDING}
        animationDuration={reduceMotion ? 0 : ENTER_DURATION_MS}
        enterTransition={reduceMotion ? NO_MOTION : undefined}
      >
        <SankeyLink getNodeColor={nodeColour} strokeOpacity={LINK_OPACITY} />
        {/* The node value label hard-codes the unit "sessions", so counts live in the tooltip instead. */}
        <SankeyNode getNodeColor={nodeColour} showValueLabels={false} />
        <SankeyTooltip formatValue={formatFailures} />
      </SankeyChart>
    </ChartFrame>
  )
}
