import { DataTable } from '@/components/primitives/DataTable'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { formatPoints } from '@/lib/stats'

import type { ScenarioRow } from './api'
import { scaleKeyLabel } from './deltaBarGeometry'
import { WORSE_THRESHOLD, scenarioDelta } from './deltaMarks'
import { scenarioColumns } from './scenarioColumns'

const TABLE_MAX_HEIGHT = 380
/** Below this the wide column set does not fit and the numbers scroll away. */
const NARROW_QUERY = '(max-width: 640px)'

/**
 * What a full-length bar means. It used to draw its own track with a centre
 * tick, which sat three hundred pixels from the tick the bars actually anchor
 * on — two axes disagreeing. Zero is now marked in the column itself, so the key
 * only has to state the extent — and at 390 there are no bars to key at all.
 */
function DeltaAxisLegend({ scale }: { readonly scale: number }) {
  return (
    <span className="hidden items-center gap-2 text-[12px] text-ink-muted sm:flex">
      <InstrumentLabel>scale</InstrumentLabel>
      <span className="num">{scaleKeyLabel(scale, (value) => formatPoints(value, 0))}</span>
      <span>· zero at the rule</span>
    </span>
  )
}

/** The largest absolute change in the suite; every bar is drawn against it. */
function deltaScale(scenarios: readonly ScenarioRow[]): number {
  return scenarios.reduce((largest, row) => Math.max(largest, Math.abs(scenarioDelta(row))), 0)
}

interface ScenarioTableProps {
  readonly scenarios: readonly ScenarioRow[]
}

export function ScenarioTable({ scenarios }: ScenarioTableProps) {
  const narrow = useMediaQuery(NARROW_QUERY)
  const worse = scenarios.filter((row) => scenarioDelta(row) < WORSE_THRESHOLD).length
  const scale = deltaScale(scenarios)

  return (
    <Panel variant="card" bodyClassName="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <InstrumentLabel>scenarios</InstrumentLabel>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="text-h3 text-ink">Every scenario in the suite</h3>
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <DeltaAxisLegend scale={scale} />
            <span className="num text-small text-ink-muted">
              {worse} of {scenarios.length} worse on head
            </span>
          </span>
        </div>
      </header>
      {scenarios.length === 0 ? (
        <p className="py-6 text-ink-muted">This check ran no scenarios.</p>
      ) : (
        <DataTable
          columns={scenarioColumns(scale, narrow)}
          rows={scenarios}
          getRowId={(row) => row.scenario}
          caption="Pass rate per scenario on base and head, with the change between them."
          maxHeight={TABLE_MAX_HEIGHT}
          initialSort={{ columnId: 'delta', direction: 'asc' }}
        />
      )}
    </Panel>
  )
}
