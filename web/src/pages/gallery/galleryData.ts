/** Typed, illustrative data for the gallery only. Nothing here is a measurement. */
import type { HeatStep } from '@/components/primitives/HeatStripe'
import type { JsonValue } from '@/components/primitives/JsonView'
import type { Outcome } from '@/components/primitives/PassFailPill'

export interface DemoRun {
  readonly id: string
  readonly task: string
  readonly tokensPerStep: readonly number[]
  readonly heat: readonly HeatStep[]
  readonly blamedStep: number | null
  readonly outcome: Outcome
  readonly costUsd: number
  readonly durationSeconds: number
}

const STEP_COUNT = 12

export const DEMO_HEAT: readonly HeatStep[] = [
  { step: 1, effect: null },
  { step: 2, effect: null },
  { step: 3, effect: 0.04 },
  { step: 4, effect: null },
  { step: 5, effect: 0.21 },
  { step: 6, effect: null },
  { step: 7, effect: 0.75 },
  { step: 8, effect: 0.38 },
  { step: 9, effect: null },
  { step: 10, effect: 0.12 },
  { step: 11, effect: null },
  { step: 12, effect: null },
]

const TASKS = [
  'refund_wrong_pnr',
  'order_duplicate',
  'seat_upgrade_loop',
  'baggage_policy',
  'cancel_no_id',
] as const

/** Deterministic pseudo-random in [0, 1) so the gallery renders identically every time. */
function seeded(seed: number): number {
  const value = Math.sin(seed * 12.9898) * 43758.5453
  return value - Math.floor(value)
}

function buildRun(index: number): DemoRun {
  const blamedStep = index % 4 === 3 ? null : 3 + (index % 7)
  const heat = Array.from({ length: STEP_COUNT }, (_, stepIndex): HeatStep => {
    const step = stepIndex + 1
    if (blamedStep === null) return { step, effect: null }
    if (step === blamedStep) return { step, effect: 0.5 + seeded(index + 1) * 0.4 }
    const tested = Math.abs(step - blamedStep) <= 2
    return { step, effect: tested ? seeded(index * 31 + step) * 0.3 : null }
  })
  return {
    id: `run-${String(500 - index).padStart(3, '0')}`,
    task: TASKS[index % TASKS.length] ?? TASKS[0],
    tokensPerStep: Array.from({ length: STEP_COUNT }, (_, step) =>
      Math.round(200 + seeded(index * 17 + step) * 900),
    ),
    heat,
    blamedStep,
    outcome: index % 3 === 0 ? 'pass' : 'fail',
    costUsd: Math.round((0.2 + seeded(index + 99) * 0.6) * 100) / 100,
    durationSeconds: Math.round(20 + seeded(index + 7) * 70),
  }
}

export const DEMO_RUN_COUNT = 500
export const DEMO_RUNS: readonly DemoRun[] = Array.from({ length: DEMO_RUN_COUNT }, (_, index) =>
  buildRun(index),
)

export const DEMO_PAYLOAD: JsonValue = {
  step: 7,
  actor: 'tool',
  tool: 'get_reservation_details',
  arguments: { reservation_id: 'NM1VX1' },
  result: { status: 'ok', cabin: 'economy', refundable: false, segments: 2 },
  from_tape: true,
  calls: 0,
}

export const DEMO_CODE = `$ bisect blame run-041 --top 3 --n 8
rewind k=7   steps 1-6 read from tape   0 calls
treated 7/8 pass   control 1/8 pass
blame: step 7   effect +0.75   95% CI [+0.41, +0.94]`
