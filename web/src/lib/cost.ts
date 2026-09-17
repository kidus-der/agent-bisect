import { formatNumber } from './format'

/**
 * What a diagnosis costs.
 *
 * Model calls are the unit the server always measures; USD is a convenience it
 * can only offer when a price list exists, which real mode has none of. So
 * calls lead everywhere — axis titles, KPI labels, table columns — and a price
 * appears beside them only when one was sent. Nothing here derives dollars from
 * calls: that would put a number on screen the run never measured.
 */
export const COST_UNIT_LABEL = 'model calls'

export function formatCalls(calls: number | null | undefined): string {
  if (calls === null || calls === undefined || !Number.isFinite(calls)) return '—'
  const whole = Math.round(calls)
  return `${formatNumber(whole, { decimals: 0 })} ${whole === 1 ? 'call' : 'calls'}`
}

/** `null` when the server sent no price, so a caller must render the absence. */
export function formatUsd(usd: number | null | undefined): string | null {
  if (usd === null || usd === undefined || !Number.isFinite(usd)) return null
  return formatNumber(usd, { decimals: 2, prefix: '$' })
}
