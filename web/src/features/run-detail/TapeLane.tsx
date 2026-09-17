import { Bot, Gavel, type LucideIcon, User, Wrench } from 'lucide-react'
import { motion } from 'motion/react'
import { memo } from 'react'

import { TapeStep, type TapeStepState } from '@/components/primitives/TapeStep'
import { type SpringName, springTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

import type { StepView } from './api'
import type { TimelineGeometry } from './timelineScale'

const ACTOR_ICONS: Readonly<Record<StepView['actor'], LucideIcon>> = {
  agent: Bot,
  user: User,
  tool: Wrench,
  evaluator: Gavel,
}

const BLAMED_SCALE = 1.08
export const ACTOR_LANE_HEIGHT = 18

interface TapeCellProps {
  readonly step: number
  readonly actor: StepView['actor']
  readonly state: TapeStepState
  readonly x: number
  readonly width: number
  readonly reduced: boolean
}

function springFor(state: TapeStepState): SpringName {
  if (state === 'tape') return 'drift'
  if (state === 'blamed') return 'settle'
  return 'snap'
}

const TapeCell = memo(function TapeCell({ step, actor, state, x, width, reduced }: TapeCellProps) {
  const Icon = ACTOR_ICONS[actor]
  return (
    <div
      className="absolute top-0 bottom-0 left-0 flex flex-col items-center"
      style={{ width, transform: `translateX(${x}px)` }}
    >
      <span
        className={cn(
          'flex items-center justify-center',
          state === 'tape' ? 'text-tape' : 'text-ink-muted',
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
        // Opacity is never used to dim a cell's own text: it would drop the step
        // number below AA. How far the replay has been scrubbed is the bar below.
        animate={{ opacity: 1, scale: state === 'blamed' ? BLAMED_SCALE : 1 }}
        // No per-cell delay: the band itself advances in slices, so the
        // left-to-right march comes from the state machine, not from 54 queued
        // animations starting in the same commit.
        transition={springTransition(springFor(state), reduced)}
      >
        <TapeStep
          step={step}
          state={state}
          size="fluid"
          // Signature moment (direction.md §7.1): the blamed cell is the one
          // glowing element on this view - a 2px amber->coral ring, not a hairline.
          // The one glowing element on this view: a 2px gradient ring, an amber
          // halo and the fill-token glow. The 1.08 scale alone was absorbed by
          // the border, so the emphasis is carried by the ring, not by size.
          className={cn(
            state === 'blamed' &&
              'p-0.5 shadow-[0_0_36px_-4px_var(--bx-blame-fill)] ring-2 ring-blame/45 ring-offset-2 ring-offset-ground',
          )}
        />
      </motion.div>
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
    <div
      aria-hidden="true"
      data-testid="tape-lane"
      className="relative"
      style={{ width: geometry.contentWidth, height }}
    >
      {steps.map((step) => (
        <TapeCell
          key={step.step_idx}
          step={step.step_idx}
          actor={step.actor}
          state={states[step.step_idx - 1] ?? 'pending'}
          x={geometry.x(step.step_idx)}
          width={geometry.bandWidth}
          reduced={reduced}
        />
      ))}
      {/* How far the replay has been scrubbed, as a mark rather than as faded text. */}
      <span className="absolute inset-x-0 bottom-0 h-px bg-line-strong" />
      <motion.span
        className="absolute bottom-0 left-0 h-0.5 origin-left bg-measure"
        style={{ width: geometry.contentWidth }}
        initial={false}
        animate={{ scaleX: (geometry.x(playhead) + geometry.bandWidth) / geometry.contentWidth }}
        transition={springTransition('settle', reduced)}
      />
    </div>
  )
}
