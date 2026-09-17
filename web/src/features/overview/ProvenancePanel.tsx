/**
 * What produced the numbers beside it. The hero states a result; this states
 * which models and which τ² commit it came from, so the claim is traceable
 * without leaving the page. Everything here is `/api/meta`, already fetched by
 * the shell's data-source flag, so it costs no extra request.
 */
import { useMetaQuery } from '@/api/queries'
import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Skeleton } from '@/components/primitives/Skeleton'

const SHORT_COMMIT_CHARS = 8

/** `nvidia/llama-3.1-nemotron-70b-instruct` -> `llama-3.1-nemotron-70b-instruct`. */
function modelName(model: string): string {
  return model.split('/').at(-1) ?? model
}

function formatGeneratedAt(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.valueOf())) return value
  return parsed.toISOString().slice(0, 16).replace('T', ' ')
}

interface RowProps {
  readonly label: string
  readonly value: string
}

function Row({ label, value }: RowProps) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="shrink-0 label-instrument">{label}</span>
      <span className="min-w-0 truncate num text-small text-ink" title={value}>
        {value}
      </span>
    </div>
  )
}

export function ProvenancePanel() {
  const meta = useMetaQuery()

  return (
    <section
      aria-label="Provenance"
      className="rounded-kpi border border-line bg-surface px-4 py-3"
    >
      <InstrumentLabel>provenance</InstrumentLabel>
      {meta.isPending ? (
        <div className="mt-2 flex flex-col gap-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-3/5" />
        </div>
      ) : meta.isError ? (
        <p className="mt-2 text-small text-ink-muted">
          Provenance is unavailable while the server cannot be reached.
        </p>
      ) : (
        <div className="mt-1 divide-y divide-line">
          <Row label="agent" value={modelName(meta.data.data.agent_model)} />
          <Row label="user sim" value={modelName(meta.data.data.user_model)} />
          <Row label="τ² commit" value={meta.data.data.tau2_commit.slice(0, SHORT_COMMIT_CHARS)} />
          <Row label="generated" value={formatGeneratedAt(meta.data.data.generated_at)} />
        </div>
      )}
    </section>
  )
}
