/** Pure colour maths used by the token generator and the contrast test. */

export type Hex = `#${string}`

export interface Rgb {
  readonly r: number
  readonly g: number
  readonly b: number
}

const HEX_PATTERN = /^#[0-9a-fA-F]{6}$/
const CHANNEL_MAX = 255

export function parseHex(hex: string): Rgb {
  if (!HEX_PATTERN.test(hex)) {
    throw new Error(`Expected a 6-digit hex colour, received "${hex}"`)
  }
  return {
    r: Number.parseInt(hex.slice(1, 3), 16),
    g: Number.parseInt(hex.slice(3, 5), 16),
    b: Number.parseInt(hex.slice(5, 7), 16),
  }
}

export function toHex({ r, g, b }: Rgb): Hex {
  const channel = (value: number): string =>
    Math.round(Math.min(CHANNEL_MAX, Math.max(0, value)))
      .toString(16)
      .padStart(2, '0')
  return `#${channel(r)}${channel(g)}${channel(b)}`.toUpperCase() as Hex
}

/** Composite `amount` (0–1) of `foreground` over an opaque `background`. */
export function mixHex(foreground: string, background: string, amount: number): Hex {
  const fg = parseHex(foreground)
  const bg = parseHex(background)
  const blend = (a: number, b: number): number => a * amount + b * (1 - amount)
  return toHex({ r: blend(fg.r, bg.r), g: blend(fg.g, bg.g), b: blend(fg.b, bg.b) })
}

export function withAlpha(hex: string, alpha: number): string {
  const { r, g, b } = parseHex(hex)
  return `rgb(${r} ${g} ${b} / ${alpha})`
}

function linearize(channel: number): number {
  const srgb = channel / CHANNEL_MAX
  return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4
}

/** WCAG 2.x relative luminance. */
export function relativeLuminance(hex: string): number {
  const { r, g, b } = parseHex(hex)
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
}

/** WCAG 2.x contrast ratio, always >= 1. */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a)
  const lb = relativeLuminance(b)
  const lighter = Math.max(la, lb)
  const darker = Math.min(la, lb)
  return (lighter + 0.05) / (darker + 0.05)
}
