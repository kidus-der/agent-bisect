import { useCallback, useRef, memo } from 'react'

import type { HeatCell } from './blame'
import { heatBucket } from './heatScale'

const HEIGHT = 20
const TICK_GAP = 1

interface TimelineMinimapProps {
  readonly cells: readonly HeatCell[]
  readonly blamedStep: number | null
  readonly playhead: number
  /** Fraction of the content scrolled past, 0..1. */
  readonly scrollFraction: number
  /** Fraction of the content visible, 0..1. */
  readonly viewportFraction: number
  readonly onScrollFraction: (fraction: number) => void
}

/**
 * The whole tape at a glance for runs too long to fit. Dragging it pans the
 * tape, which is how touch users move around a 60-step run.
 */
function TimelineMinimapImpl({
  cells,
  blamedStep,
  playhead,
  scrollFraction,
  viewportFraction,
  onScrollFraction,
}: TimelineMinimapProps) {
  const trackRef = useRef<HTMLDivElement | null>(null)

  const panTo = useCallback(
    (clientX: number): void => {
      const track = trackRef.current
      if (!track) return
      const rect = track.getBoundingClientRect()
      if (rect.width === 0) return
      const centred = (clientX - rect.left) / rect.width - viewportFraction / 2
      onScrollFraction(Math.min(Math.max(centred, 0), 1))
    },
    [onScrollFraction, viewportFraction],
  )

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
    event.currentTarget.setPointerCapture(event.pointerId)
    panTo(event.clientX)
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    panTo(event.clientX)
  }

  const total = Math.max(cells.length, 1)
  return (
    <div
      ref={trackRef}
      data-testid="timeline-minimap"
      aria-hidden="true"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      className="relative mt-3 w-full cursor-grab touch-none overflow-hidden rounded-step border border-line bg-ground active:cursor-grabbing"
      style={{ height: HEIGHT }}
    >
      <div className="absolute inset-0 flex items-stretch">
        {cells.map((cell) => (
          <span
            key={cell.step}
            className={cell.tested ? '' : 'hatch'}
            style={{
              flex: '1 1 0',
              marginRight: TICK_GAP,
              background:
                cell.step === blamedStep && cell.tested
                  ? 'linear-gradient(90deg, var(--bx-blame-fill), var(--bx-blame-coral-fill))'
                  : cell.tested
                    ? heatBucket(cell.effect ?? 0)
                    : undefined,
            }}
          />
        ))}
      </div>
      <span
        className="absolute inset-y-0 border-x-2 border-measure bg-measure/10"
        style={{
          left: `${scrollFraction * 100}%`,
          width: `${Math.min(viewportFraction, 1) * 100}%`,
        }}
      />
      <span
        className="absolute inset-y-0 w-px bg-ink"
        style={{ left: `${((playhead - 0.5) / total) * 100}%` }}
      />
    </div>
  )
}

/**
 * Memoised: a rewind tick re-renders the page several times a second, and none
 * of this panel's inputs change while the tape is replaying.
 */
export const TimelineMinimap = memo(TimelineMinimapImpl)
