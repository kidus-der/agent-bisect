import { Rewind, RotateCcw } from 'lucide-react'
import { useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import useMeasure from 'react-use-measure'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { formatEffect, formatInterval } from '@/lib/format'
import { cn } from '@/lib/utils'

import type { StepView } from './api'
import { BlameHeatStripe } from './BlameHeatStripe'
import type { HeatCell } from './blame'
import { TapeLane } from './TapeLane'
import type { RewindState } from './tapeState'
import type { TapeStepState } from '@/components/primitives/TapeStep'
import { TimelineMinimap } from './TimelineMinimap'
import { TimelinePlayhead } from './TimelinePlayhead'
import { clampStep, timelineGeometry } from './timelineScale'

const TAPE_HEIGHT = 62
const BAND_HEIGHT = 16
const HEAT_HEIGHT = 14
const AXIS_HEIGHT = 16
const PAGE_STEP = 5
const SCROLL_MARGIN_PX = 48
const AXIS_TICK_TARGET = 8

interface Intervention {
  readonly before: string
  readonly after: string
}

interface StepTimelineProps {
  readonly steps: readonly StepView[]
  readonly states: readonly TapeStepState[]
  readonly cells: readonly HeatCell[]
  readonly blamedStep: number | null
  readonly playhead: number
  readonly onPlayheadChange: (step: number) => void
  readonly rewind: RewindState | null
  readonly onRewind: () => void
  readonly onResetRewind: () => void
  readonly canRewind: boolean
  readonly rerunCount: number | null
  readonly intervention: Intervention | null
}

function axisTicks(nSteps: number): readonly number[] {
  const stride = Math.max(1, Math.ceil(nSteps / AXIS_TICK_TARGET))
  const ticks = [1]
  for (let step = stride; step <= nSteps; step += stride) {
    if (step !== 1) ticks.push(step)
  }
  if (ticks.at(-1) !== nSteps) ticks.push(nSteps)
  return ticks
}

function valueText(step: StepView | undefined, index: number, total: number): string {
  if (!step) return `step ${index} of ${total}`
  const what = step.tool_name ? `${step.actor} ${step.tool_name}` : step.actor
  return `step ${step.step_idx} of ${total}, ${what}`
}

function readout(cell: HeatCell | undefined): string {
  if (!cell) return ''
  if (!cell.tested) return 'not tested · no effect estimated'
  return `effect ${formatEffect(cell.effect ?? 0)} ${formatInterval(cell.low ?? 0, cell.high ?? 0)}`
}

/**
 * The tape: the page's focal element. One slider drives the playhead, the
 * inspector and the "replay up to here" state of every cell.
 */
export function StepTimeline({
  steps,
  states,
  cells,
  blamedStep,
  playhead,
  onPlayheadChange,
  rewind,
  onRewind,
  onResetRewind,
  canRewind,
  rerunCount,
  intervention,
}: StepTimelineProps) {
  const reduced = useReducedMotion() ?? false
  const [frameRef, frame] = useMeasure({ debounce: 0 })
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const sliderRef = useRef<HTMLDivElement | null>(null)
  const [scrollLeft, setScrollLeft] = useState(0)
  const [hovered, setHovered] = useState<number | null>(null)
  // The step the drag last committed. A pointer crossing a cell fires many
  // moves; only the ones that change the step are worth a render.
  const committedRef = useRef(playhead)

  const nSteps = steps.length
  const geometry = useMemo(
    () => timelineGeometry({ nSteps, availableWidth: frame.width }),
    [nSteps, frame.width],
  )
  const ticks = useMemo(() => axisTicks(nSteps), [nSteps])

  const setFromClientX = useCallback(
    (clientX: number): void => {
      const rect = sliderRef.current?.getBoundingClientRect()
      if (!rect) return
      const next = geometry.stepAt(clientX - rect.left)
      if (next === committedRef.current) return
      committedRef.current = next
      onPlayheadChange(next)
    },
    [geometry, onPlayheadChange],
  )

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    const moves: Readonly<Record<string, number>> = {
      ArrowLeft: -1,
      ArrowDown: -1,
      ArrowRight: 1,
      ArrowUp: 1,
      PageUp: PAGE_STEP,
      PageDown: -PAGE_STEP,
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      onPlayheadChange(event.key === 'Home' ? 1 : nSteps)
      return
    }
    const delta = moves[event.key]
    if (delta === undefined) return
    event.preventDefault()
    onPlayheadChange(clampStep(playhead + delta, nSteps))
  }

  // Keyboard, the forest plot and the matrix all move the playhead too.
  useEffect(() => {
    committedRef.current = playhead
  }, [playhead])

  // Keep the playhead in view when it moves by keyboard or by a rewind.
  useEffect(() => {
    const node = scrollRef.current
    if (!node || !geometry.scrolls) return
    const centre = geometry.center(playhead)
    const min = node.scrollLeft + SCROLL_MARGIN_PX
    const max = node.scrollLeft + node.clientWidth - SCROLL_MARGIN_PX
    if (centre >= min && centre <= max) return
    node.scrollTo({
      left: Math.max(0, centre - node.clientWidth / 2),
      behavior: reduced ? 'auto' : 'smooth',
    })
  }, [playhead, geometry, reduced])

  // The scroll container fills the measured frame, so its viewport is that width.
  const viewport = frame.width
  const viewportFraction = geometry.contentWidth > 0 ? viewport / geometry.contentWidth : 1
  const scrollFraction = geometry.contentWidth > 0 ? scrollLeft / geometry.contentWidth : 0
  const activeCell = cells[(hovered ?? playhead) - 1]
  const tapeBandWidth = rewind ? geometry.x(rewind.step) : 0
  const rerunBandStart = rewind ? geometry.x(Math.min(rewind.step + 1, nSteps)) : 0

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <InstrumentLabel as="h2">tape</InstrumentLabel>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRewind}
            disabled={!canRewind}
            title={
              canRewind ? undefined : `Step ${playhead} was never tested, so it cannot be re-run`
            }
            className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-control border border-line-strong bg-elevated px-2.5 text-small font-medium text-ink hover:border-ink-muted disabled:cursor-not-allowed disabled:text-ink-muted disabled:opacity-60"
          >
            <Rewind aria-hidden="true" className="size-3.5" />
            Rewind to k={playhead}
          </button>
          {rewind ? (
            <button
              type="button"
              onClick={onResetRewind}
              className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-control border border-line px-2.5 text-small text-ink-muted hover:text-ink"
            >
              <RotateCcw aria-hidden="true" className="size-3.5" />
              Recording
            </button>
          ) : null}
        </div>
      </div>

      <div ref={frameRef} className="relative">
        {/* Edge fades tell you the tape continues; they never sit over the first cell. */}
        <div
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-ground to-transparent transition-opacity',
            scrollLeft > 2 ? 'opacity-100' : 'opacity-0',
          )}
        />
        <div
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-ground to-transparent transition-opacity',
            scrollFraction + viewportFraction < 0.995 ? 'opacity-100' : 'opacity-0',
          )}
        />
        <div
          ref={scrollRef}
          onScroll={(event) => setScrollLeft(event.currentTarget.scrollLeft)}
          className={cn(
            '[scrollbar-width:none] overflow-x-auto overflow-y-hidden [&::-webkit-scrollbar]:hidden',
            geometry.scrolls ? '' : 'flex justify-center',
          )}
        >
          <div
            ref={sliderRef}
            role="slider"
            tabIndex={0}
            aria-label="Step playhead"
            aria-valuemin={1}
            aria-valuemax={nSteps}
            aria-valuenow={playhead}
            aria-valuetext={valueText(steps[playhead - 1], playhead, nSteps)}
            onKeyDown={handleKeyDown}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId)
              setFromClientX(event.clientX)
            }}
            onPointerMove={(event) => {
              if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
              setFromClientX(event.clientX)
            }}
            // pan-y keeps vertical page scrolling; the minimap pans a long tape.
            className="cursor-ew-resize touch-pan-y rounded-step select-none"
            style={{ width: geometry.contentWidth }}
          >
            <TimelinePlayhead
              geometry={geometry}
              step={playhead}
              reduced={reduced}
              glowing={rewind !== null && rewind.phase !== 'settled'}
            />
            <TapeLane
              steps={steps}
              states={states}
              geometry={geometry}
              playhead={playhead}
              height={TAPE_HEIGHT}
              reduced={reduced}
            />
            <div
              aria-hidden="true"
              className="relative"
              style={{ width: geometry.contentWidth, height: BAND_HEIGHT }}
            >
              <span
                className={cn(
                  'absolute top-1 left-0 truncate border-x border-b border-line-strong px-1 text-center font-mono text-[10px] leading-3 tracking-wide text-ink-muted uppercase transition-opacity',
                  rewind && tapeBandWidth > 0 ? 'opacity-100' : 'opacity-0',
                )}
                style={{ width: Math.max(tapeBandWidth - geometry.bandWidth * 0.14, 0) }}
              >
                read from tape · 0 calls
              </span>
              <span
                className={cn(
                  'absolute top-1 truncate border-x border-b border-measure px-1 text-center font-mono text-[10px] leading-3 tracking-wide text-measure uppercase transition-opacity',
                  rewind && rewind.step < nSteps ? 'opacity-100' : 'opacity-0',
                )}
                style={{
                  left: rerunBandStart,
                  width: Math.max(geometry.contentWidth - rerunBandStart, 0),
                }}
              >
                re-run live{rerunCount === null ? '' : ` × ${rerunCount}`}
              </span>
            </div>
            <BlameHeatStripe
              cells={cells}
              geometry={geometry}
              blamedStep={blamedStep}
              height={HEAT_HEIGHT}
              onHoverStep={setHovered}
            />
            <div
              aria-hidden="true"
              className="relative"
              style={{ width: geometry.contentWidth, height: AXIS_HEIGHT }}
            >
              {ticks.map((tick) => (
                <span
                  key={tick}
                  className="absolute top-0.5 num text-[10px] leading-none text-ink-muted"
                  style={{ left: geometry.center(tick), transform: 'translateX(-50%)' }}
                >
                  {tick}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {geometry.scrolls ? (
        <TimelineMinimap
          cells={cells}
          blamedStep={blamedStep}
          playhead={playhead}
          scrollFraction={scrollFraction}
          viewportFraction={viewportFraction}
          onScrollFraction={(fraction) =>
            scrollRef.current?.scrollTo({ left: fraction * geometry.contentWidth })
          }
        />
      ) : null}

      <p
        aria-live="polite"
        className="mt-3 flex min-h-5 flex-wrap items-baseline gap-x-2 border-t border-line pt-3 font-mono text-small"
      >
        <span className="font-medium text-ink">step {hovered ?? playhead}</span>
        <span className="num text-ink-muted">{readout(activeCell)}</span>
      </p>
      {intervention ? (
        <p className="mt-1 flex flex-wrap items-baseline gap-x-2 font-mono text-small">
          <span className="font-medium text-blame">step {rewind?.step ?? playhead}</span>
          <span className="text-ink-muted">tool result replaced</span>
          <span>
            <span className="text-ink-muted line-through">{intervention.before}</span>
            {' → '}
            <span className="font-medium text-ink">{intervention.after}</span>
          </span>
        </p>
      ) : null}
    </div>
  )
}
