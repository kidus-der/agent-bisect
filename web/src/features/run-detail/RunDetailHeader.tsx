import { Link } from '@tanstack/react-router'
import { ArrowLeft, FlaskConical, Radio } from 'lucide-react'
import { motion } from 'motion/react'

import { BlameBadge } from '@/components/primitives/BlameBadge'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { layoutIds, useSpringTransition } from '@/design/motion'
import { formatNumber } from '@/lib/format'

import type { RunDetail } from './api'
import type { BlameVerdict } from './blame'

interface RunDetailHeaderProps {
  /** The id the page asked for; the payload's own id may be missing. */
  readonly runId: string
  readonly run: RunDetail
  readonly verdict: BlameVerdict | null
  readonly simulated: boolean
}

function Fact({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-ink-muted">{label} </span>
      <span className="num text-ink">{value}</span>
    </span>
  )
}

/** Everything true about this run, above the tape. */
export function RunDetailHeader({ runId, run, verdict, simulated }: RunDetailHeaderProps) {
  const transition = useSpringTransition('glide')
  const recording = run.status === 'recording'
  const id = run.run_id || runId

  return (
    <header className="flex flex-col gap-3">
      <title>{`${id} · Bisect`}</title>
      <Link
        to="/runs"
        className="inline-flex w-fit items-center gap-1.5 text-small text-ink-muted hover:text-ink"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" />
        Runs
      </Link>

      {/* The Runs row morphs into this strip. */}
      <motion.div
        layoutId={layoutIds.runRow(id)}
        transition={transition}
        className="flex flex-wrap items-center gap-x-3 gap-y-2"
      >
        <h1 className="font-mono text-h1 text-ink">{id}</h1>
        <span className="text-h3 text-ink-muted">{run.task_id}</span>
        {recording ? (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-pill border border-measure/40 bg-measure-tint px-2 text-small text-measure">
            <Radio aria-hidden="true" className="size-3.5" />
            Recording
          </span>
        ) : run.outcome ? (
          <PassFailPill outcome={run.outcome} />
        ) : null}
        {simulated ? (
          <span
            data-testid="run-simulated-flag"
            className="inline-flex h-6 items-center gap-1.5 rounded-pill border border-line-strong px-2 text-[11px] text-ink-muted"
          >
            <FlaskConical aria-hidden="true" className="size-3" />
            Simulated data
          </span>
        ) : null}
      </motion.div>

      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-small">
        <Fact label="domain" value={run.domain} />
        <Fact label="model" value={run.agent_model} />
        <Fact label="steps" value={String(run.steps.length)} />
        <Fact
          label="reward"
          value={run.reward === null ? 'not scored yet' : formatNumber(run.reward, { decimals: 2 })}
        />
        {run.seed === null ? null : <Fact label="seed" value={String(run.seed)} />}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {verdict ? (
          <BlameBadge
            step={verdict.step}
            effect={verdict.effect}
            interval={[verdict.low, verdict.high]}
          />
        ) : null}
        {run.planted_step !== null && run.fault_type !== null ? (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-pill border border-line-strong bg-elevated px-2 font-mono text-[11px] text-ink-muted">
            planted fault · {run.fault_type} at step {run.planted_step}
          </span>
        ) : null}
      </div>
    </header>
  )
}
