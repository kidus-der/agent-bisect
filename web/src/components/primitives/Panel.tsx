import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { InstrumentLabel } from './InstrumentLabel'

/**
 * Radius and elevation vary together on purpose (direction.md §4): no two panel
 * kinds share both, so a screen never reads as a grid of identical cards.
 */
export type PanelVariant = 'card' | 'kpi' | 'chart' | 'canvas' | 'elevated'

interface PanelProps {
  readonly variant?: PanelVariant
  /** Instrument label, rendered `LIKE_THIS_`. */
  readonly label?: string
  readonly title?: string
  readonly actions?: ReactNode
  readonly children: ReactNode
  readonly className?: string
  readonly bodyClassName?: string
  readonly as?: 'section' | 'div' | 'article'
}

const VARIANT_STYLES: Readonly<Record<PanelVariant, string>> = {
  card: 'rounded-card border-line bg-surface border',
  // Secondary tiles recede rather than lift, and take the stronger hairline: in
  // the light theme a fill above the page read as an empty white box.
  kpi: 'rounded-kpi border-line-strong bg-recessed border',
  chart: 'rounded-chart border-line bg-surface border',
  // Blueprint canvas: square corners so the registration marks land on them.
  // Slate at 60%: the dashed frame stays quiet in dark and stops disappearing in light.
  canvas: 'border-tape/60 bg-ground blueprint-dots border border-dashed',
  elevated: 'rounded-modal border-line-strong bg-elevated border',
}

const VARIANT_PADDING: Readonly<Record<PanelVariant, string>> = {
  card: 'p-5',
  kpi: 'p-4',
  chart: 'p-4',
  canvas: 'p-6',
  elevated: 'p-5',
}

const CORNERS = [
  '-top-1.5 -left-1.5',
  '-top-1.5 -right-1.5',
  '-bottom-1.5 -left-1.5',
  '-right-1.5 -bottom-1.5',
]

/** Hairline cross-ticks at the corners: "measured", without saying so. Canvases only. */
function RegistrationMarks() {
  return (
    <>
      {CORNERS.map((position) => (
        <svg
          key={position}
          aria-hidden="true"
          viewBox="0 0 12 12"
          className={cn('pointer-events-none absolute size-3 text-ink-muted', position)}
        >
          <path d="M6 0v12M0 6h12" stroke="currentColor" strokeWidth={1} />
        </svg>
      ))}
    </>
  )
}

export function Panel({
  variant = 'card',
  label,
  title,
  actions,
  children,
  className,
  bodyClassName,
  as: Tag = 'section',
}: PanelProps) {
  const hasHeader = Boolean(label ?? title ?? actions)
  return (
    <Tag
      data-variant={variant}
      className={cn(
        'relative min-w-0',
        VARIANT_STYLES[variant],
        VARIANT_PADDING[variant],
        className,
      )}
    >
      {variant === 'canvas' ? <RegistrationMarks /> : null}
      {hasHeader ? (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            {label ? <InstrumentLabel>{label}</InstrumentLabel> : null}
            {title ? <h3 className="truncate text-h3 text-ink">{title}</h3> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </Tag>
  )
}
