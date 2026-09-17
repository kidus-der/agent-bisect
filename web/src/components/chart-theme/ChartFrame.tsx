import { type ReactNode, useId } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { cn } from '@/lib/utils'

interface ChartFrameProps {
  /** Instrument label: `recall@m`. */
  readonly label: string
  readonly title: string
  /** Text alternative: what the chart shows and its key numbers. */
  readonly description: string
  readonly children: ReactNode
  /** Tailwind height class for the plot area. */
  readonly heightClassName?: string
  readonly legend?: ReactNode
  readonly className?: string
}

/** Wraps any Bklit chart: 8px chart radius, instrument label, and a real text alternative. */
export function ChartFrame({
  label,
  title,
  description,
  children,
  heightClassName = 'h-56',
  legend,
  className,
}: ChartFrameProps) {
  const titleId = useId()
  const descriptionId = useId()
  return (
    <Panel variant="chart" className={className}>
      <figure aria-labelledby={titleId} aria-describedby={descriptionId} className="m-0">
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <InstrumentLabel>{label}</InstrumentLabel>
            <h3 id={titleId} className="truncate text-h3 text-ink">
              {title}
            </h3>
          </div>
          {legend}
        </header>
        <p id={descriptionId} className="sr-only">
          {description}
        </p>
        <div className={cn('relative w-full min-w-0', heightClassName)}>{children}</div>
      </figure>
    </Panel>
  )
}

export interface LegendEntry {
  readonly label: string
  readonly colour: string
  /** Dashed swatch for a control / reference series. */
  readonly dashed?: boolean
}

interface ChartLegendProps {
  readonly entries: readonly LegendEntry[]
}

export function ChartLegend({ entries }: ChartLegendProps) {
  return (
    <ul className="flex shrink-0 flex-wrap justify-end gap-x-3 gap-y-1 text-[12px] text-ink-muted">
      {entries.map((entry) => (
        <li key={entry.label} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={cn('h-0 w-3 border-t-2', entry.dashed && 'border-dashed')}
            style={{ borderColor: entry.colour }}
          />
          {entry.label}
        </li>
      ))}
    </ul>
  )
}
