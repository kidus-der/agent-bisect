/**
 * Single source of truth for Bisect's design tokens.
 *
 * Values come from docs/design/direction.md §4. `tokens-css.ts` turns these
 * objects into the CSS variables for both themes and the Tailwind `@theme`
 * mapping; nothing else in the app may hard-code a colour, radius or size.
 */
import { type Hex, mixHex } from './color'

export const THEME_NAMES = ['dark', 'light'] as const
export type ThemeName = (typeof THEME_NAMES)[number]

export interface NeutralColors {
  readonly ground: Hex
  readonly surface: Hex
  readonly elevated: Hex
  /** Decorative hairline. Never the only carrier of meaning. */
  readonly line: Hex
  /** Decorative stronger hairline for control edges and blueprint ticks. */
  readonly lineStrong: Hex
  /** Blueprint dot-grid texture. Quieter than any hairline so text stays clean on top of it. */
  readonly dot: Hex
  readonly text: Hex
  readonly muted: Hex
  readonly focus: Hex
}

/** Semantic roles. Amber/coral mean blame and nothing else. */
export interface RoleColors {
  readonly blame: Hex
  readonly blameCoral: Hex
  readonly measure: Hex
  readonly judge: Hex
  readonly pass: Hex
  readonly fail: Hex
  /** From-tape slate: non-text marks only (3:1), on ground/surface only. */
  readonly tape: Hex
}

export type RoleName = keyof RoleColors

/**
 * Blame as a *fill*. No text sits on it, so the AA text floor that drags the
 * light theme's amber down to `#9C5B08` does not apply — and that value was the
 * bug: at 1.01:1 against the fail red it has the *same luminance*, which is why
 * a blamed heat cell was indistinguishable from a failure beside it.
 *
 * A fill is still a data mark, so it must clear 3:1 on `surface` (WCAG 1.4.11);
 * the vivid `#F5A524` manages only 2.04:1 on white. The light theme therefore
 * keeps the amber hue and darkens just far enough to clear the mark floor while
 * staying well clear of the fail red's luminance.
 */
export interface FillColors {
  readonly blame: Hex
  readonly blameCoral: Hex
}

/**
 * Sequential heat ramp anchors. Every step between them is a data mark and
 * clears 3:1 on `surface` (WCAG 1.4.11) — the dark end of the light ramp goes
 * past `role.measure` toward ink so all five steps stay separable on white.
 */
export interface HeatAnchors {
  readonly from: Hex
  readonly to: Hex
}

/** Text colours that sit on top of a solid role fill. */
export interface OnRoleColors {
  readonly onRole: Hex
  readonly onTape: Hex
}

export interface ThemeTokens {
  readonly scheme: ThemeName
  readonly neutral: NeutralColors
  readonly role: RoleColors
  readonly fill: FillColors
  readonly heat: HeatAnchors
  readonly on: OnRoleColors
  /** How much of a role colour is composited over `surface` for opaque tints. */
  readonly tintAmount: number
}

const dark: ThemeTokens = {
  scheme: 'dark',
  neutral: {
    ground: '#0B0D12',
    surface: '#12151C',
    elevated: '#191D27',
    line: '#242A37',
    lineStrong: '#343C4E',
    dot: '#2A3140',
    text: '#E8EBF2',
    muted: '#8A93A6',
    focus: '#4CC9F0',
  },
  role: {
    blame: '#F5A524',
    blameCoral: '#F7625B',
    measure: '#4CC9F0',
    judge: '#A78BFA',
    pass: '#3DD68C',
    fail: '#F25F5C',
    tape: '#5B6478',
  },
  fill: { blame: '#F5A524', blameCoral: '#F7625B' },
  heat: { from: '#2E6D83', to: '#4CC9F0' },
  on: { onRole: '#0B0D12', onTape: '#FFFFFF' },
  tintAmount: 0.14,
}

const light: ThemeTokens = {
  scheme: 'light',
  neutral: {
    ground: '#F5F6F8',
    surface: '#FFFFFF',
    elevated: '#FBFBFD',
    line: '#DEE2E9',
    lineStrong: '#C5CBD6',
    dot: '#D6DBE3',
    text: '#12141B',
    muted: '#5B6478',
    // direction.md keeps #4CC9F0 here, but that is 1.9:1 on white; the ring must
    // clear 3:1 (WCAG 1.4.11), so light uses the light measurement cyan.
    focus: '#0B7398',
  },
  role: {
    blame: '#9C5B08',
    blameCoral: '#C93838',
    measure: '#0B7398',
    judge: '#7250D6',
    pass: '#0F7A4C',
    fail: '#C63432',
    tape: '#5B6478',
  },
  fill: { blame: '#C4841D', blameCoral: '#E8574F' },
  heat: { from: '#509AB5', to: '#0E4860' },
  on: { onRole: '#FFFFFF', onTape: '#FFFFFF' },
  tintAmount: 0.08,
}

export const themes: Readonly<Record<ThemeName, ThemeTokens>> = { dark, light }

export const ROLE_NAMES = [
  'blame',
  'blameCoral',
  'measure',
  'judge',
  'pass',
  'fail',
  'tape',
] as const satisfies readonly RoleName[]

/** Opaque role tint: the role composited over `surface`. Pills and chips use it. */
export function roleTint(theme: ThemeTokens, role: RoleName): Hex {
  return mixHex(theme.role[role], theme.neutral.surface, theme.tintAmount)
}

/**
 * Chart series order (direction.md §4). Blame amber is last and reserved: it is
 * never handed to an arbitrary series, only to a series that *is* blame.
 */
export const CHART_SERIES_ORDER = [
  'measure',
  'judge',
  'pass',
  'fail',
  'tape',
  'blame',
] as const satisfies readonly RoleName[]

/** Steps of the sequential (heatmap) scale, interpolated between the theme's anchors. */
export const SEQUENTIAL_SCALE_STEPS = 5

export function sequentialScale(theme: ThemeTokens): readonly Hex[] {
  const last = SEQUENTIAL_SCALE_STEPS - 1
  return Array.from({ length: SEQUENTIAL_SCALE_STEPS }, (_, index) =>
    mixHex(theme.heat.to, theme.heat.from, index / last),
  )
}

/** Radii are deliberately varied per surface type (direction.md §4). */
export const radii = {
  step: '4px',
  control: '6px',
  chart: '8px',
  kpi: '10px',
  card: '12px',
  modal: '16px',
  pill: '999px',
} as const
export type RadiusName = keyof typeof radii

/** 4px base unit. */
export const spacing = {
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  6: '24px',
  8: '32px',
  12: '48px',
  16: '64px',
} as const

export interface TypeStyle {
  readonly sizePx: number
  readonly linePx: number
  readonly weight: number
  readonly tracking?: string
  readonly mono?: boolean
  readonly uppercase?: boolean
}

export const typeScale = {
  display: { sizePx: 44, linePx: 48, weight: 650, tracking: '-0.02em' },
  h1: { sizePx: 28, linePx: 34, weight: 600, tracking: '-0.01em' },
  h2: { sizePx: 20, linePx: 28, weight: 600 },
  h3: { sizePx: 15, linePx: 22, weight: 600 },
  body: { sizePx: 14, linePx: 20, weight: 400 },
  small: { sizePx: 13, linePx: 18, weight: 400 },
  micro: { sizePx: 11, linePx: 16, weight: 500, tracking: '0.04em', mono: true, uppercase: true },
  stat: { sizePx: 32, linePx: 32, weight: 600, mono: true },
} as const satisfies Record<string, TypeStyle>
export type TypeScaleName = keyof typeof typeScale

export const fonts = {
  sans: "'Geist Variable', ui-sans-serif, system-ui, sans-serif",
  mono: "'Geist Mono Variable', ui-monospace, 'SF Mono', Menlo, monospace",
} as const

/** No drop shadows: elevation is border + fill step. Glow is one-per-view. */
export const GLOW_ALPHA = 0.35
export const glowRoles = ['blame', 'measure'] as const satisfies readonly RoleName[]

export const zIndex = {
  base: 0,
  sticky: 10,
  nav: 20,
  overlay: 40,
  palette: 50,
  toast: 60,
  skipLink: 100,
} as const

export const breakpoints = {
  /** Below this the top nav collapses into the bottom tab bar. */
  navCollapse: 768,
  min: 390,
  max: 1920,
} as const

export const THEME_STORAGE_KEY = 'bisect.theme'
