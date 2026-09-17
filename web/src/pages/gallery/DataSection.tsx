import { CodeBlock } from '@/components/primitives/CodeBlock'
import { DataTable, type DataTableColumn } from '@/components/primitives/DataTable'
import { DiffBlock } from '@/components/primitives/DiffBlock'
import { HeatStripe } from '@/components/primitives/HeatStripe'
import { JsonView } from '@/components/primitives/JsonView'
import { Panel } from '@/components/primitives/Panel'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { StepSparkline } from '@/components/primitives/StepSparkline'
import { formatNumber } from '@/lib/format'

import { Specimen } from './GallerySection'
import { DEMO_CODE, DEMO_PAYLOAD, DEMO_RUNS, DEMO_RUN_COUNT, type DemoRun } from './galleryData'

const TABLE_MAX_HEIGHT = 360

const RUN_COLUMNS: ReadonlyArray<DataTableColumn<DemoRun>> = [
  {
    id: 'id',
    header: 'Run',
    cell: (run) => <span className="font-mono font-medium text-ink">{run.id}</span>,
    sortValue: (run) => run.id,
  },
  {
    id: 'task',
    header: 'Task',
    cell: (run) => <span className="font-mono text-ink-muted">{run.task}</span>,
    sortValue: (run) => run.task,
    hideOnMobile: true,
  },
  {
    id: 'tokens',
    header: 'Tokens / step',
    cell: (run) => (
      <StepSparkline
        values={run.tokensPerStep}
        label="tokens per step"
        markIndex={run.blamedStep === null ? undefined : run.blamedStep - 1}
      />
    ),
    hideOnMobile: true,
  },
  {
    id: 'blame',
    header: 'Effect by step',
    cell: (run) => (
      <HeatStripe steps={run.heat} blamedStep={run.blamedStep ?? undefined} cellWidth={10} />
    ),
    sortValue: (run) => run.blamedStep,
  },
  {
    id: 'status',
    header: 'Status',
    cell: (run) => <PassFailPill outcome={run.outcome} size="sm" />,
    sortValue: (run) => run.outcome,
  },
  {
    id: 'cost',
    header: 'Cost',
    numeric: true,
    cell: (run) => formatNumber(run.costUsd, { decimals: 2, prefix: '$' }),
    sortValue: (run) => run.costUsd,
  },
  {
    id: 'duration',
    header: 'Duration',
    numeric: true,
    hideOnMobile: true,
    cell: (run) => formatNumber(run.durationSeconds, { suffix: 's' }),
    sortValue: (run) => run.durationSeconds,
  },
]

export function DataSection() {
  return (
    <div className="flex flex-col gap-10">
      <Specimen
        name="DataTable"
        note={`${DEMO_RUN_COUNT} illustrative rows · virtualized · sortable · sticky header`}
      >
        <Panel variant="card" className="p-0!" bodyClassName="overflow-hidden rounded-card">
          <DataTable
            caption="Illustrative runs"
            columns={RUN_COLUMNS}
            rows={DEMO_RUNS}
            getRowId={(run) => run.id}
            maxHeight={TABLE_MAX_HEIGHT}
          />
        </Panel>
      </Specimen>
      <div className="grid grid-cols-1 gap-x-8 gap-y-10 lg:grid-cols-2">
        <Specimen name="DiffBlock" note="− what the tape said · + the intervention">
          <DiffBlock
            label="intervention · step 7"
            before={'get_reservation_details → { "reservation_id": "NM1VX1" }'}
            after={'get_reservation_details → { "reservation_id": "ZFA04Y" }'}
          />
        </Specimen>
        <Specimen name="CodeBlock" note="Geist Mono · copyable">
          <CodeBlock label="terminal" code={DEMO_CODE} />
        </Specimen>
        <Specimen name="JsonView" note="neutral syntax tones only" className="lg:col-span-2">
          <JsonView label="step 7 · payload" value={DEMO_PAYLOAD} />
        </Specimen>
      </div>
    </div>
  )
}
