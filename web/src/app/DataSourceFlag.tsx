import type { ReactNode } from 'react'

import { useMetaQuery } from '@/api/queries'
import { Tooltip } from '@/components/primitives/Tooltip'
import { cn } from '@/lib/utils'

const FLAG_BASE =
  'rounded-step inline-flex h-6 items-center gap-1.5 border px-2 font-mono text-[11px] font-medium tracking-wide whitespace-nowrap uppercase'

interface FlagProps {
  readonly explanation: string
  readonly className: string
  readonly children: ReactNode
  readonly testId?: string
}

/** A button so the explanation tooltip is reachable by keyboard and touch. */
function Flag({ explanation, className, children, testId }: FlagProps) {
  return (
    <Tooltip content={explanation} side="bottom">
      <button
        type="button"
        data-testid={testId}
        className={cn(FLAG_BASE, 'cursor-help', className)}
      >
        {children}
      </button>
    </Tooltip>
  )
}

/**
 * Persistent slot driven by `/api/meta`. Simulated data is flagged with the same
 * hatch that marks untested steps: hatch always means "not measured".
 */
export function DataSourceFlag() {
  const { data, isPending, isError } = useMetaQuery()

  if (isPending) {
    return (
      <span role="status" className={cn(FLAG_BASE, 'border-line text-ink-muted')}>
        <span className="sr-only">Checking data source</span>
        <span aria-hidden="true">data · …</span>
      </span>
    )
  }
  if (isError || !data) {
    return (
      <Flag
        explanation="The dashboard cannot reach bisect serve on 127.0.0.1:8484."
        className="border-dashed border-line-strong text-ink-muted"
      >
        <span aria-hidden="true" className="size-1.5 rounded-full border border-ink-muted" />
        API offline
      </Flag>
    )
  }
  if (data.meta.simulated) {
    return (
      <Flag
        testId="simulated-flag"
        explanation="Fixture-backed responses. Every number on screen is synthetic, not measured."
        className="relative overflow-hidden border-ink-muted bg-elevated text-ink"
      >
        <span aria-hidden="true" className="absolute inset-0 hatch opacity-70" />
        <span className="relative bg-elevated px-1">
          Simulated<span className="hidden sm:inline"> data</span>
        </span>
      </Flag>
    )
  }
  return (
    <Flag
      explanation={`Recorded runs · ${data.data.agent_model}`}
      className="border-line text-ink-muted"
    >
      <span aria-hidden="true" className="size-1.5 rounded-full bg-ink-muted" />
      Recorded<span className="hidden sm:inline"> data</span>
    </Flag>
  )
}
