import { Bot, type LucideIcon, User, Wrench } from 'lucide-react'
import { motion } from 'motion/react'
import { memo } from 'react'

import { TapeStep, type TapeStepState } from '@/components/primitives/TapeStep'
import { type SpringName, STAGGER_SECONDS, springTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

import type { StepView } from './api'
import type { TimelineGeometry } from './timelineScale'

const ACTOR_ICONS: Readonly<Record<StepView['actor'], LucideIcon>> = {
  agent: Bot,
  user: User,
  tool: Wrench,
}

const BLAMED_SCALE = 1.08
/** Caps the left-to-right rewind stagger so a 60-step tape still settles quickly. */
const MAX_STAGGER_SECONDS = 0.6
export const ACTOR_LANE_HEIGHT = 18

interface TapeCellProps {
  readonly step: number
  readonly actor: StepView['actor']
  readonly state: TapeStepState
  readonly x: number
  readonly width: number
  readonly isPlayhead: boolean
  readonly reduced: boolean
}

function springFor(state: TapeStepState): SpringName {
  if (state === 'tape') return 'drift'
  if (state === 'blamed') return 'settle'
  return 'snap'
}

const TapeCell = memo(function TapeCell({
  step,
  actor,
  state,
  x,
  width,
  isPlayhead,
  reduced,
}: TapeCellProps) {
  const Icon = ACTOR_ICONS[actor]
  const delay =
    reduced || state !== 'tape'
      ? 0
      : Math.min((step - 1) * STAGGER_SECONDS.rewind, MAX_STAGGER_SECONDS)
  return (
    <div
      className="absolute top-0 bottom-0 left-0 flex flex-col items-center"
      style={{ width, transform: `translateX(${x}px)` }}
    >
      <span
        className={cn(
          'flex items-center justify-center',
          state === 'tape' ? 'text-tape' : 'text-ink-muted',
          state === 'pending' && 'opacity-45',
        )}
        style={{ height: ACTOR_LANE_HEIGHT }}
      >
        <Icon aria-hidden="true" className="size-3" strokeWidth={2} />
      </span>
      <motion.div
        // Re-mounting on state change pops the new state in; colour itself never tweens.
        key={state}
        className={cn('w-full', state === 'blamed' && 'relative z-10')}
        initial={reduced ? false : { opacity: 0.2, scale: 0.88 }}
        animate={{
          opacity: state === 'pending' ? 0.5 : 1,
          scale: state === 'blamed' ? BLAMED_SCALE : 1,
        }}
        transition={{ ...springTransition(springFor(state), reduced), delay }}
      >
        <TapeStep step={step} state={state} size="fluid" />
      </motion.div>
      {isPlayhead ? (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 -bottom-0.5 h-0.5 bg-measure"
        />
      ) : null}
    </div>
  )
})

interface TapeLaneProps {
  readonly steps: readonly StepView[]
  readonly states: readonly TapeStepState[]
  readonly geometry: TimelineGeometry
  readonly playhead: number
  readonly height: number
  readonly reduced: boolean
}

/** The tape itself: an actor glyph lane over the step cells, both on the band scale. */
export function TapeLane({ steps, states, geometry, playhead, height, reduced }: TapeLaneProps) {
  return (
    <div aria-hidden="true" className="relative" style={{ width: geometry.contentWidth, height }}>
      {steps.map((step) => (
        <TapeCell
          key={step.step_idx}
          step={step.step_idx}
          actor={step.actor}
          state={states[step.step_idx - 1] ?? 'pending'}
          x={geometry.x(step.step_idx)}
          width={geometry.bandWidth}
          isPlayhead={step.step_idx === playhead}
          reduced={reduced}
        />
      ))}
    </div>
  )
}
