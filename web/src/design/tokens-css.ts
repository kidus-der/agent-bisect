/**
 * Generator: tokens.ts -> CSS. `scripts/generate-tokens.ts` writes the result to
 * `tokens.generated.css`, which index.css imports, so both themes exist as plain
 * CSS before first paint (no runtime injection, no flash of the wrong theme).
 */
import { withAlpha } from './color'
import {
  CHART_SERIES_ORDER,
  GLOW_ALPHA,
  ROLE_NAMES,
  THEME_NAMES,
  type ThemeName,
  type ThemeTokens,
  fonts,
  glowRoles,
  radii,
  roleTint,
  sequentialScale,
  themes,
  typeScale,
  zIndex,
} from './tokens'

type Declarations = ReadonlyArray<readonly [name: string, value: string]>

const ROOT_FONT_PX = 16
const CHROME_GLOW_ALPHA = 0.14
const TOOLTIP_ALPHA = 0.92

export function kebab(name: string): string {
  return name.replace(/[A-Z]/g, (char) => `-${char.toLowerCase()}`)
}

function rem(px: number): string {
  return `${px / ROOT_FONT_PX}rem`
}

function glow(colour: string, alpha: number): string {
  return `0 0 24px -8px ${withAlpha(colour, alpha)}`
}

function bisectDeclarations(theme: ThemeTokens): Declarations {
  const neutrals = Object.entries(theme.neutral).map(
    ([name, value]) => [`--bx-${kebab(name)}`, value] as const,
  )
  const roles = ROLE_NAMES.flatMap((role) => [
    [`--bx-${kebab(role)}`, theme.role[role]] as const,
    [`--bx-${kebab(role)}-tint`, roleTint(theme, role)] as const,
  ])
  const glows = glowRoles.map(
    (role) => [`--bx-glow-${kebab(role)}`, glow(theme.role[role], GLOW_ALPHA)] as const,
  )
  return [
    ...neutrals,
    ...roles,
    ['--bx-blame-fill', theme.fill.blame],
    ['--bx-blame-coral-fill', theme.fill.blameCoral],
    ['--bx-on-role', theme.on.onRole],
    ['--bx-on-tape', theme.on.onTape],
    ...glows,
    ['--bx-glow-chrome', glow(theme.neutral.text, CHROME_GLOW_ALPHA)],
    ['--bx-scrim', withAlpha(theme.neutral.ground, 0.72)],
  ]
}

/** shadcn/ui semantic aliases, expressed in Bisect tokens. */
function shadcnDeclarations(): Declarations {
  return [
    ['--background', 'var(--bx-ground)'],
    ['--foreground', 'var(--bx-text)'],
    ['--card', 'var(--bx-surface)'],
    ['--card-foreground', 'var(--bx-text)'],
    ['--popover', 'var(--bx-elevated)'],
    ['--popover-foreground', 'var(--bx-text)'],
    ['--primary', 'var(--bx-text)'],
    ['--primary-foreground', 'var(--bx-ground)'],
    ['--secondary', 'var(--bx-elevated)'],
    ['--secondary-foreground', 'var(--bx-text)'],
    ['--muted', 'var(--bx-elevated)'],
    ['--muted-foreground', 'var(--bx-muted)'],
    ['--accent', 'var(--bx-elevated)'],
    ['--accent-foreground', 'var(--bx-text)'],
    ['--destructive', 'var(--bx-fail)'],
    ['--border', 'var(--bx-line)'],
    ['--input', 'var(--bx-line-strong)'],
    ['--ring', 'var(--bx-focus)'],
  ]
}

/** The chart theme bridge: every variable the Bklit charts read. */
function chartDeclarations(theme: ThemeTokens): Declarations {
  const series = CHART_SERIES_ORDER.map(
    (role, index) => [`--chart-${index + 1}`, `var(--bx-${kebab(role)})`] as const,
  )
  const scale = sequentialScale(theme).map(
    (value, index) => [`--chart-scale-0${index + 1}`, value] as const,
  )
  return [
    ...series,
    ...scale,
    ['--chart-scale-pattern-color', 'var(--bx-surface)'],
    ['--chart-background', 'var(--bx-surface)'],
    ['--chart-foreground', 'var(--bx-text)'],
    ['--chart-foreground-muted', 'var(--bx-muted)'],
    ['--chart-label', 'var(--bx-muted)'],
    ['--chart-grid', 'var(--bx-line)'],
    ['--chart-brush-border', 'var(--bx-line)'],
    ['--chart-crosshair', 'var(--bx-muted)'],
    ['--chart-line-primary', 'var(--chart-1)'],
    ['--chart-line-secondary', 'var(--chart-2)'],
    ['--chart-indicator-color', 'var(--chart-1)'],
    ['--chart-indicator-secondary-color', 'var(--chart-2)'],
    ['--chart-segment-background', 'var(--bx-elevated)'],
    ['--chart-segment-line', 'var(--bx-line-strong)'],
    ['--chart-tooltip-background', withAlpha(theme.neutral.elevated, TOOLTIP_ALPHA)],
    ['--chart-tooltip-foreground', 'var(--bx-text)'],
    ['--chart-tooltip-muted', 'var(--bx-muted)'],
    ['--chart-marker-background', 'var(--bx-elevated)'],
    ['--chart-marker-border', 'var(--bx-line-strong)'],
    ['--chart-marker-foreground', 'var(--bx-text)'],
    ['--chart-marker-badge-background', 'var(--bx-elevated)'],
    ['--chart-marker-badge-foreground', 'var(--bx-text)'],
  ]
}

export function themeDeclarations(name: ThemeName): Declarations {
  const theme = themes[name]
  return [
    ['color-scheme', theme.scheme],
    ...bisectDeclarations(theme),
    ...shadcnDeclarations(),
    ...chartDeclarations(theme),
  ]
}

const BISECT_COLOR_UTILITIES: Declarations = [
  ['ground', '--bx-ground'],
  ['surface', '--bx-surface'],
  ['elevated', '--bx-elevated'],
  ['line', '--bx-line'],
  ['line-strong', '--bx-line-strong'],
  ['ink', '--bx-text'],
  ['ink-muted', '--bx-muted'],
  ['focus', '--bx-focus'],
  ['blame-fill', '--bx-blame-fill'],
  ['blame-coral-fill', '--bx-blame-coral-fill'],
  ['on-role', '--bx-on-role'],
  ['on-tape', '--bx-on-tape'],
  ...ROLE_NAMES.flatMap((role) => [
    [kebab(role), `--bx-${kebab(role)}`] as const,
    [`${kebab(role)}-tint`, `--bx-${kebab(role)}-tint`] as const,
  ]),
]

const PASSTHROUGH_COLOR_UTILITIES = [
  'background',
  'foreground',
  'card',
  'card-foreground',
  'popover',
  'popover-foreground',
  'primary',
  'primary-foreground',
  'secondary',
  'secondary-foreground',
  'muted',
  'muted-foreground',
  'accent',
  'accent-foreground',
  'destructive',
  'border',
  'input',
  'ring',
  'chart-1',
  'chart-2',
  'chart-3',
  'chart-4',
  'chart-5',
  'chart-scale-01',
  'chart-scale-02',
  'chart-scale-03',
  'chart-scale-04',
  'chart-scale-05',
  'chart-scale-pattern-color',
  'chart-background',
  'chart-foreground',
  'chart-foreground-muted',
  'chart-label',
  'chart-grid',
  'chart-crosshair',
  'chart-tooltip-background',
  'chart-tooltip-foreground',
  'chart-tooltip-muted',
  'chart-marker-background',
  'chart-marker-border',
  'chart-marker-foreground',
] as const

function tailwindThemeDeclarations(): Declarations {
  const typography = Object.entries(typeScale).flatMap(([name, style]) => {
    const base: Array<readonly [string, string]> = [
      [`--text-${name}`, rem(style.sizePx)],
      [`--text-${name}--line-height`, rem(style.linePx)],
      [`--text-${name}--font-weight`, String(style.weight)],
    ]
    return 'tracking' in style
      ? [...base, [`--text-${name}--letter-spacing`, style.tracking] as const]
      : base
  })
  return [
    ['--font-sans', fonts.sans],
    ['--font-mono', fonts.mono],
    ['--font-heading', 'var(--font-sans)'],
    ...BISECT_COLOR_UTILITIES.map(
      ([utility, variable]) => [`--color-${utility}`, `var(${variable})`] as const,
    ),
    ...PASSTHROUGH_COLOR_UTILITIES.map((name) => [`--color-${name}`, `var(--${name})`] as const),
    ...Object.entries(radii).map(([name, value]) => [`--radius-${name}`, value] as const),
    ...typography,
    ['--shadow-glow-blame', 'var(--bx-glow-blame)'],
    ['--shadow-glow-measure', 'var(--bx-glow-measure)'],
    ['--shadow-glow-chrome', 'var(--bx-glow-chrome)'],
  ]
}

/** Theme-independent variables that Tailwind has no namespace for. */
function staticDeclarations(): Declarations {
  return Object.entries(zIndex).map(
    ([name, value]) => [`--z-${kebab(name)}`, String(value)] as const,
  )
}

function block(selector: string, declarations: Declarations): string {
  const body = declarations.map(([name, value]) => `  ${name}: ${value};`).join('\n')
  return `${selector} {\n${body}\n}`
}

const THEME_SELECTORS: Readonly<Record<ThemeName, string>> = {
  // Dark-first: dark is also the value when no data-theme has been set yet.
  dark: ':root,\n:root[data-theme="dark"]',
  light: ':root[data-theme="light"]',
}

export const GENERATED_BANNER =
  '/* GENERATED from src/design/tokens.ts by scripts/generate-tokens.ts. Do not edit. */'

export function buildTokensCss(): string {
  const themeBlocks = THEME_NAMES.map((name) =>
    block(THEME_SELECTORS[name], themeDeclarations(name)),
  )
  const themeMapping = block('@theme inline', tailwindThemeDeclarations())
  const staticBlock = block(':root', staticDeclarations())
  return [GENERATED_BANNER, staticBlock, ...themeBlocks, themeMapping].join('\n\n') + '\n'
}
