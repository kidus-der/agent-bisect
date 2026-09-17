/**
 * Chart theme bridge, JS side. The Bklit charts read CSS variables, and
 * tokens-css.ts defines every one of them for both themes, so a chart re-themes
 * with no re-render. These helpers hand those variables to chart props.
 */
import { CHART_SERIES_ORDER, type RoleName } from '@/design/tokens'
import { kebab } from '@/design/tokens-css'

export function roleColour(role: RoleName): string {
  return `var(--bx-${kebab(role)})`
}

/** Series available to arbitrary data. Blame amber is excluded: it only ever means blame. */
const ASSIGNABLE_SERIES = CHART_SERIES_ORDER.filter((role) => role !== 'blame')

/** Colour for the n-th ordinary series, in the fixed order cyan, violet, pass, fail, slate. */
export function seriesColour(index: number): string {
  const role = ASSIGNABLE_SERIES[index % ASSIGNABLE_SERIES.length] ?? 'measure'
  return roleColour(role)
}

export const chartColours = {
  background: 'var(--chart-background)',
  grid: 'var(--chart-grid)',
  label: 'var(--chart-label)',
  foreground: 'var(--chart-foreground)',
  /** Treated vs control is always cyan vs slate. */
  treated: roleColour('measure'),
  control: roleColour('tape'),
  judge: roleColour('judge'),
  pass: roleColour('pass'),
  fail: roleColour('fail'),
  /** Only for a series that *is* blame. */
  blame: roleColour('blame'),
} as const
