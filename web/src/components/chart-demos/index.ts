import { type JSX, type LazyExoticComponent, lazy } from 'react'

export interface ChartDemo {
  /** The exact Bklit registry slug, e.g. `area-chart`. */
  readonly slug: string
  readonly Component: LazyExoticComponent<() => JSX.Element>
}

/**
 * One demo per installed Bklit chart. Every entry is a dynamic import, so no
 * chart code (visx, d3, the vendored sources) lands in the initial bundle.
 */
export const CHART_DEMOS: ReadonlyArray<ChartDemo> = [
  {
    slug: 'area-chart',
    Component: lazy(() => import('./AreaChartDemo').then((m) => ({ default: m.AreaChartDemo }))),
  },
  {
    slug: 'bar-chart',
    Component: lazy(() => import('./BarChartDemo').then((m) => ({ default: m.BarChartDemo }))),
  },
  {
    slug: 'line-chart',
    Component: lazy(() => import('./LineChartDemo').then((m) => ({ default: m.LineChartDemo }))),
  },
  {
    slug: 'live-line-chart',
    Component: lazy(() =>
      import('./LiveLineChartDemo').then((m) => ({ default: m.LiveLineChartDemo })),
    ),
  },
  {
    slug: 'heatmap-chart',
    Component: lazy(() =>
      import('./HeatmapChartDemo').then((m) => ({ default: m.HeatmapChartDemo })),
    ),
  },
  {
    slug: 'gauge-chart',
    Component: lazy(() => import('./GaugeChartDemo').then((m) => ({ default: m.GaugeChartDemo }))),
  },
  {
    slug: 'ring-chart',
    Component: lazy(() => import('./RingChartDemo').then((m) => ({ default: m.RingChartDemo }))),
  },
  {
    slug: 'radar-chart',
    Component: lazy(() => import('./RadarChartDemo').then((m) => ({ default: m.RadarChartDemo }))),
  },
  {
    slug: 'scatter-chart',
    Component: lazy(() =>
      import('./ScatterChartDemo').then((m) => ({ default: m.ScatterChartDemo })),
    ),
  },
  {
    slug: 'funnel-chart',
    Component: lazy(() =>
      import('./FunnelChartDemo').then((m) => ({ default: m.FunnelChartDemo })),
    ),
  },
  {
    slug: 'sankey-chart',
    Component: lazy(() =>
      import('./SankeyChartDemo').then((m) => ({ default: m.SankeyChartDemo })),
    ),
  },
]
