import { useState } from 'react'

import { ActorGlyph } from '@/components/primitives/ActorGlyph'
import { BlameBadge } from '@/components/primitives/BlameBadge'
import { EffectWithCI } from '@/components/primitives/EffectWithCI'
import { HeatStripe } from '@/components/primitives/HeatStripe'
import { Kbd } from '@/components/primitives/Kbd'
import { Panel } from '@/components/primitives/Panel'
import { PassFailPill } from '@/components/primitives/PassFailPill'
import { SegmentedControl } from '@/components/primitives/SegmentedControl'
import { StatTicker } from '@/components/primitives/StatTicker'
import { StepSparkline } from '@/components/primitives/StepSparkline'
import { Tabs } from '@/components/primitives/Tabs'
import { TapeStep, type TapeStepState } from '@/components/primitives/TapeStep'
import { Tooltip } from '@/components/primitives/Tooltip'

import { Specimen } from './GallerySection'
import { DEMO_HEAT, DEMO_RUNS } from './galleryData'

const TAPE_STATES: readonly TapeStepState[] = [
  'live',
  'ran',
  'tape',
  'blamed',
  'failed',
  'passed',
  'pending',
]

type Arm = 'treated' | 'control' | 'both'
const ARM_OPTIONS = [
  { value: 'treated', label: 'Treated' },
  { value: 'control', label: 'Control' },
  { value: 'both', label: 'Both' },
] as const

const DELTA = 0.2

function TickerSpecimen() {
  const [runs, setRuns] = useState(8)
  return (
    <Specimen name="StatTicker" note="springs to its value · tabular numerals">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Panel variant="kpi">
          <StatTicker label="re-runs" value={runs} caption="per arm" />
        </Panel>
        <Panel variant="kpi">
          <StatTicker
            label="effect"
            value={runs / 16 + 0.25}
            decimals={2}
            signed
            caption="treated − control"
          />
        </Panel>
        <Panel variant="kpi" className="col-span-2 sm:col-span-1">
          <StatTicker
            label="cost"
            value={runs * 0.42}
            decimals={2}
            prefix="$"
            caption="this bisect"
          />
        </Panel>
      </div>
      <button
        type="button"
        onClick={() => setRuns((current) => (current >= 12 ? 4 : current + 4))}
        className="mt-3 inline-flex h-9 cursor-pointer items-center rounded-control border border-line-strong bg-elevated px-3 text-small font-medium text-ink"
      >
        Change N
      </button>
    </Specimen>
  )
}

function TapeSpecimen() {
  const [selected, setSelected] = useState(4)
  return (
    <Specimen name="TapeStep" note="4px radius · state is glyph + border, never colour alone">
      <ul className="flex flex-wrap gap-x-3 gap-y-4">
        {TAPE_STATES.map((state, index) => (
          <li key={state} className="flex flex-col items-center gap-2">
            <TapeStep
              step={index + 1}
              state={state}
              selected={selected === index + 1}
              onSelect={setSelected}
            />
            <span className="label-instrument">{state}</span>
          </li>
        ))}
      </ul>
    </Specimen>
  )
}

export function PrimitivesSection() {
  const [arm, setArm] = useState<Arm>('both')
  const run = DEMO_RUNS[0]
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-10 lg:grid-cols-2">
      <Specimen name="PassFailPill" note="✓ / ✕ glyph + word">
        <div className="flex flex-wrap items-center gap-2">
          <PassFailPill outcome="pass" />
          <PassFailPill outcome="fail" />
          <PassFailPill outcome="pass" label="7/8 pass" size="sm" />
          <PassFailPill outcome="fail" label="1/8 pass" size="sm" />
        </div>
      </Specimen>
      <Specimen name="BlameBadge" note="the only amber on the page · always with its number">
        <div className="flex flex-wrap items-center gap-3">
          <BlameBadge step={7} effect={0.75} interval={[0.41, 0.94]} />
          <BlameBadge step={4} effect={0.62} />
          <BlameBadge step={11} effect={0.31} size="sm" />
        </div>
      </Specimen>
      <Specimen name="EffectWithCI" note="estimate never without its interval · dashed line is δ">
        <ul className="flex flex-col gap-2">
          <li>
            <EffectWithCI estimate={0.04} low={-0.18} high={0.26} delta={DELTA} />
          </li>
          <li>
            <EffectWithCI estimate={0.38} low={0.07} high={0.66} delta={DELTA} />
          </li>
          <li>
            <EffectWithCI estimate={0.75} low={0.41} high={0.94} delta={DELTA} blamed />
          </li>
          <li>
            <EffectWithCI estimate={-0.12} low={-0.4} high={0.15} variant="text" />
          </li>
        </ul>
      </Specimen>
      <Specimen name="HeatStripe" note="untested steps are hatched, never a guessed colour">
        <div className="flex flex-col items-start gap-3">
          <HeatStripe steps={DEMO_HEAT} blamedStep={7} cellWidth={22} cellHeight={22} />
          <HeatStripe steps={DEMO_HEAT} blamedStep={7} />
          <HeatStripe steps={DEMO_HEAT.map((entry) => ({ ...entry, effect: null }))} />
        </div>
      </Specimen>
      <TickerSpecimen />
      <TapeSpecimen />
      <Specimen name="StepSparkline · ActorGlyph" note="row-sized marks">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {run ? (
            <StepSparkline values={run.tokensPerStep} label="tokens per step" markIndex={6} />
          ) : null}
          <ActorGlyph actor="agent" showLabel />
          <ActorGlyph actor="user" showLabel />
          <ActorGlyph actor="tool" showLabel />
        </div>
      </Specimen>
      <Specimen name="SegmentedControl · Kbd · Tooltip">
        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl label="Arm" options={ARM_OPTIONS} value={arm} onChange={setArm} />
          <span className="inline-flex items-center gap-1">
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </span>
          <Tooltip content="δ: the smallest effect that counts as blame">
            <button
              type="button"
              className="cursor-help text-small text-ink underline decoration-ink-muted decoration-dotted underline-offset-4"
            >
              What is δ?
            </button>
          </Tooltip>
        </div>
      </Specimen>
      <Specimen name="Tabs" note="one shared-layout underline" className="lg:col-span-2">
        <Tabs
          label="Step inspector"
          items={[
            {
              value: 'payload',
              label: 'Payload',
              content: <p className="text-ink-muted">What the tape recorded at this step.</p>,
            },
            {
              value: 'diff',
              label: 'Intervention',
              content: <p className="text-ink-muted">What was replaced before the re-run.</p>,
            },
            {
              value: 'outcomes',
              label: 'Outcomes',
              content: (
                <p className="text-ink-muted">Treated and control results, one mark per re-run.</p>
              ),
            },
          ]}
        />
      </Specimen>
    </div>
  )
}
