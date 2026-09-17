import type { ReactNode } from 'react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { cn } from '@/lib/utils'

interface GallerySectionProps {
  readonly id: string
  readonly index: string
  readonly title: string
  readonly description: string
  readonly children: ReactNode
}

export function GallerySection({ id, index, title, description, children }: GallerySectionProps) {
  const headingId = `${id}-heading`
  return (
    <section aria-labelledby={headingId} className="scroll-mt-20 border-t border-line pt-8" id={id}>
      <div className="mb-6 flex flex-col gap-1.5">
        <InstrumentLabel>{`${index} · ${id}`}</InstrumentLabel>
        <h2 id={headingId} className="text-h2 text-ink">
          {title}
        </h2>
        <p className="max-w-prose text-pretty text-ink-muted">{description}</p>
      </div>
      {children}
    </section>
  )
}

interface SpecimenProps {
  readonly name: string
  readonly note?: string
  readonly children: ReactNode
  readonly className?: string
}

/** One labelled specimen: the component name in mono, then the thing itself. */
export function Specimen({ name, note, children, className }: SpecimenProps) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <code className="font-mono text-small font-medium text-ink">{name}</code>
        {note ? <span className="text-[12px] text-ink-muted">{note}</span> : null}
      </div>
      {children}
    </div>
  )
}
