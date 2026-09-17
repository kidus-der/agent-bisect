import { EmptyState } from '@/components/primitives/EmptyState'
import { ErrorState } from '@/components/primitives/ErrorState'
import { Panel, type PanelVariant } from '@/components/primitives/Panel'
import { LoadingRegion, Skeleton, TableSkeleton } from '@/components/primitives/Skeleton'

import { Specimen } from './GallerySection'

const PANEL_NOTES: Readonly<Record<PanelVariant, string>> = {
  kpi: '10px · surface',
  card: '12px · surface',
  chart: '8px · surface',
  canvas: '0px · dashed · blueprint dots · registration marks',
  elevated: '16px · elevated fill · stronger hairline',
}

const PANEL_ORDER: readonly PanelVariant[] = ['kpi', 'card', 'chart', 'elevated', 'canvas']

export function PanelsSection() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {PANEL_ORDER.map((variant) => (
        <Panel
          key={variant}
          variant={variant}
          label={variant}
          title={`Panel · ${variant}`}
          className={variant === 'canvas' ? 'sm:col-span-2 lg:col-span-1' : undefined}
        >
          <p className="text-small text-ink-muted">{PANEL_NOTES[variant]}</p>
        </Panel>
      ))}
    </div>
  )
}

export function StatesSection() {
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-10 lg:grid-cols-2">
      <Specimen name="Skeleton" note="sweep stops under reduced motion · tied to a real request">
        <Panel variant="card">
          <LoadingRegion subject="illustrative table">
            <div className="mb-4 flex items-center gap-3">
              <Skeleton className="h-8 w-24" />
              <Skeleton className="h-6 w-16 rounded-pill" />
            </div>
            <TableSkeleton rows={4} />
          </LoadingRegion>
        </Panel>
      </Specimen>
      <Specimen name="ErrorState" note="message + machine code + retry">
        <Panel variant="card">
          <ErrorState
            title="Cannot reach the Bisect server"
            message="Cannot reach the Bisect server. Is `bisect serve` running?"
            code="network_error"
            onRetry={() => undefined}
          />
        </Panel>
      </Specimen>
      <Specimen
        name="EmptyState"
        note="an empty tape and the command that fills it"
        className="lg:col-span-2"
      >
        <Panel variant="card">
          <EmptyState
            label="no runs recorded"
            title="The tape is empty"
            description="Record a batch of τ² airline tasks. Each run is written to tape so it can be replayed with zero network calls."
            command="bisect record --domain airline --tasks 0-19"
          />
        </Panel>
      </Specimen>
    </div>
  )
}
