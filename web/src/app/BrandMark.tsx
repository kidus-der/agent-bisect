/**
 * The product in one glyph: a tape, cut at one step. Neutral ink plus measurement
 * cyan only: amber and coral mean blame, so the chrome never spends them.
 */
export function BrandMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 28 20" className="h-5 w-7 shrink-0">
      <path d="M0 10h28" stroke="var(--bx-line-strong)" strokeWidth="1.5" />
      <rect x="1" y="5" width="6" height="10" rx="1.5" fill="var(--bx-tape)" />
      {/* The bisected step: one tall cell, split down the middle. */}
      <rect x="10" y="1.5" width="3.25" height="17" rx="1.25" fill="var(--bx-text)" />
      <rect x="14.75" y="1.5" width="3.25" height="17" rx="1.25" fill="var(--bx-text)" />
      <rect
        x="21.25"
        y="5.75"
        width="5.5"
        height="8.5"
        rx="1.25"
        fill="var(--bx-ground)"
        stroke="var(--bx-measure)"
        strokeWidth="1.5"
      />
    </svg>
  )
}
