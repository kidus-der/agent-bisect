/**
 * The sequential single-hue scale for the accuracy matrix.
 *
 * Every cell prints its value, so every fill has to clear AA against the text
 * drawn on it. Holding the text at one colour caps the dark ramp at a mix of
 * about 0.45 — five teals a few points apart that read as one — so each step
 * instead carries whichever ink clears AA against it, and the steps are chosen
 * to skip the mid band where neither ink does.
 */
import { type Hex, contrastRatio, mixHex } from '@/design/color'
import { type ThemeName, themes } from '@/design/tokens'

export const HEATMAP_STEPS = 5
const AA_TEXT = 4.5
/** Lightest step: a tint, still distinct from the panel it sits on. */
const MIN_MIX = 0.06
const MIX_STEP = 0.01

export interface HeatmapStep {
  readonly fill: Hex
  /** The ink that clears AA on this fill. */
  readonly text: Hex
}

/** Every mix of the hue over the surface on which some ink clears AA. */
function legibleMixes(theme: ThemeName): readonly HeatmapStep[] {
  const { role, neutral, on } = themes[theme]
  const inks = [neutral.text, on.onRole] as const
  const steps: HeatmapStep[] = []
  for (let amount = MIN_MIX; amount <= 1 + MIX_STEP / 2; amount += MIX_STEP) {
    const fill = mixHex(role.measure, neutral.surface, Math.min(1, amount))
    const best = inks.reduce((winner, ink) =>
      contrastRatio(fill, ink) > contrastRatio(fill, winner) ? ink : winner,
    )
    if (contrastRatio(fill, best) >= AA_TEXT) steps.push({ fill, text: best })
  }
  return steps
}

/**
 * `HEATMAP_STEPS` fills, weakest first.
 *
 * Ordered by how much hue is mixed in, not by luminance: on a dark surface more
 * hue means a *brighter* fill and on a light one a darker fill, so luminance
 * order is inverted between the themes while hue order is not. The five are
 * spaced evenly across the legible mixes, which steps over the mid band where
 * neither ink clears AA.
 */
export function heatmapRamp(theme: ThemeName): readonly HeatmapStep[] {
  const legible = legibleMixes(theme)
  if (legible.length === 0) {
    const { role, neutral } = themes[theme]
    const fallback = mixHex(role.measure, neutral.surface, MIN_MIX)
    return Array.from({ length: HEATMAP_STEPS }, () => ({
      fill: fallback,
      text: neutral.text,
    }))
  }

  const last = legible.length - 1
  return Array.from({ length: HEATMAP_STEPS }, (_, index) => {
    const at = Math.round((last * index) / (HEATMAP_STEPS - 1))
    return legible[at] ?? legible[last]
  }) as readonly HeatmapStep[]
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
