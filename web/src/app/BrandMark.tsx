/** The product in one glyph: a tape of steps, one of them blamed. */
export function BrandMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 28 20" className="h-5 w-7 shrink-0">
      <defs>
        <linearGradient id="brand-blame" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--bx-blame)" />
          <stop offset="1" stopColor="var(--bx-blame-coral)" />
        </linearGradient>
      </defs>
      <path d="M0 10h28" stroke="var(--bx-line-strong)" strokeWidth="1.5" />
      <rect x="1" y="5" width="6" height="10" rx="1.5" fill="var(--bx-tape)" />
      <rect x="10.5" y="1.5" width="7" height="17" rx="1.5" fill="url(#brand-blame)" />
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
