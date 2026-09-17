/** Number formatting shared by every estimate, interval and ticker. */

const MINUS_SIGN = '−'
const DEFAULT_EFFECT_DECIMALS = 2

/** Signed effect: `+0.75`, `−0.12`, `0.00`. Uses a real minus sign for column alignment. */
export function formatEffect(value: number, decimals: number = DEFAULT_EFFECT_DECIMALS): string {
  if (!Number.isFinite(value)) return 'n/a'
  const magnitude = Math.abs(value).toFixed(decimals)
  if (Number(magnitude) === 0) return magnitude
  return `${value > 0 ? '+' : MINUS_SIGN}${magnitude}`
}

/** Confidence interval: `[+0.52, +0.91]`. */
export function formatInterval(
  low: number,
  high: number,
  decimals: number = DEFAULT_EFFECT_DECIMALS,
): string {
  return `[${formatEffect(low, decimals)}, ${formatEffect(high, decimals)}]`
}

export interface NumberFormatOptions {
  readonly decimals?: number
  readonly prefix?: string
  readonly suffix?: string
  readonly signed?: boolean
}

export function formatNumber(value: number, options: NumberFormatOptions = {}): string {
  const { decimals = 0, prefix = '', suffix = '', signed = false } = options
  if (!Number.isFinite(value)) return 'n/a'
  const body = signed
    ? formatEffect(value, decimals)
    : value.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
  return `${prefix}${body}${suffix}`
}
