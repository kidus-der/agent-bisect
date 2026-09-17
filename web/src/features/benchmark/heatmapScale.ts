/**
 * The sequential single-hue scale for the accuracy matrix.
 *
 * Every cell prints its value, so every fill has to clear AA against the body
 * text in both themes. The shared `sequentialScale` token runs all the way to
 * full measurement cyan, which does not (mid-cyan is a contrast trap: too light
 * for the light ink, too dark for the dark ink). This builds the ramp instead by
 * walking the mix amount down until the darkest step still clears 4.5:1, so the
 * number in the cell is always legible without a plate behind it.
 */
import { type Hex, contrastRatio, mixHex } from '@/design/color'
import { type ThemeName, themes } from '@/design/tokens'

export const HEATMAP_STEPS = 5
const AA_CONTRAST = 4.5
/** Lightest step: a tint, still distinct from the panel it sits on. */
const MIN_MIX = 0.08
const MIX_SEARCH_START = 1
const MIX_SEARCH_STEP = 0.01

/** Largest mix of the hue over the surface whose fill still clears AA for cell text. */
function maxLegibleMix(theme: ThemeName): number {
  const { role, neutral } = themes[theme]
  for (let amount = MIX_SEARCH_START; amount > MIN_MIX; amount -= MIX_SEARCH_STEP) {
    const fill = mixHex(role.measure, neutral.surface, amount)
    if (contrastRatio(fill, neutral.text) >= AA_CONTRAST) return amount
  }
  return MIN_MIX
}

/** `HEATMAP_STEPS` fills, lightest first. Stable for a theme, so memoise at the call site. */
export function heatmapRamp(theme: ThemeName): readonly Hex[] {
  const { role, neutral } = themes[theme]
  const maxMix = maxLegibleMix(theme)
  const span = maxMix - MIN_MIX
  return Array.from({ length: HEATMAP_STEPS }, (_, index) =>
    mixHex(role.measure, neutral.surface, MIN_MIX + (span * index) / (HEATMAP_STEPS - 1)),
  )
}

export interface RampDomain {
  readonly min: number
  readonly max: number
}

/** The observed range, so the ramp is spent on the values that actually occur. */
export function rampDomain(values: readonly number[]): RampDomain {
  if (values.length === 0) return { min: 0, max: 1 }
  return { min: Math.min(...values), max: Math.max(...values) }
}

/** Index into the ramp for a value. Equal min and max put everything at the top step. */
export function rampStep(value: number, domain: RampDomain): number {
  const span = domain.max - domain.min
  if (!Number.isFinite(value) || span <= 0) return HEATMAP_STEPS - 1
  const fraction = (value - domain.min) / span
  const step = Math.round(fraction * (HEATMAP_STEPS - 1))
  return Math.min(HEATMAP_STEPS - 1, Math.max(0, step))
}
