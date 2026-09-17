import type { ReactNode } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'

interface PageHeaderProps {
  readonly label: string
  readonly title: string
  readonly description?: string
  readonly actions?: ReactNode
}

/** Page title on a fading blueprint band: the texture lives in headers, never in tables. */
export function PageHeader({ label, title, description, actions }: PageHeaderProps) {
  return (
    <header className="relative -mx-4 mb-6 px-4 pb-6 lg:-mx-8 lg:mb-8 lg:px-8">
      {/* React 19 hoists <title> into <head>: each route names the document. */}
      <title>{`${title} · Bisect`}</title>
      <div
        aria-hidden="true"
        className="absolute inset-x-0 -top-8 bottom-0 blueprint-dots [mask-image:linear-gradient(to_bottom,black,transparent)] opacity-60"
      />
      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <InstrumentLabel>{label}</InstrumentLabel>
          <h1 className="text-h1 text-ink">{title}</h1>
          {description ? (
            <p className="max-w-prose text-pretty text-ink-muted">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  )
}
