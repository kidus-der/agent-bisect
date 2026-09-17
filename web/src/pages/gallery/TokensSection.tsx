import { contrastRatio } from '@/design/color'
import { springs } from '@/design/motion'
import { useTheme } from '@/design/theme'
import { ROLE_NAMES, radii, themes, typeScale } from '@/design/tokens'
import { kebab } from '@/design/tokens-css'
import { cn } from '@/lib/utils'

import { Specimen } from './GallerySection'

const NEUTRAL_NAMES = [
  'ground',
  'surface',
  'elevated',
  'line',
  'lineStrong',
  'text',
  'muted',
] as const

const ROLE_MEANINGS: Readonly<Record<(typeof ROLE_NAMES)[number], string>> = {
  blame: 'blame · reserved',
  blameCoral: 'blame gradient end',
  measure: 'measurement · replay',
  judge: 'LLM judge',
  pass: 'pass',
  fail: 'fail',
  tape: 'from tape · non-text',
}

interface SwatchProps {
  readonly name: string
  readonly hex: string
  readonly caption: string
}

function Swatch({ name, hex, caption }: SwatchProps) {
  return (
    <li className="flex items-center gap-3">
      <span
        aria-hidden="true"
        className="size-10 shrink-0 rounded-control border border-line-strong"
        style={{ backgroundColor: hex }}
      />
      <span className="flex min-w-0 flex-col">
        <span className="text-small font-medium text-ink">{name}</span>
        <span className="num text-[12px] text-ink-muted">
          {hex} · {caption}
        </span>
      </span>
    </li>
  )
}

export function TokensSection() {
  const { theme } = useTheme()
  const tokens = themes[theme]
  const onSurface = (hex: string): string =>
    `${contrastRatio(hex, tokens.neutral.surface).toFixed(2)}:1`
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-10 lg:grid-cols-2">
      <Specimen name="neutrals" note={`theme: ${theme} · ratio is against surface`}>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {NEUTRAL_NAMES.map((name) => (
            <Swatch
              key={name}
              name={kebab(name)}
              hex={tokens.neutral[name]}
              caption={onSurface(tokens.neutral[name])}
            />
          ))}
        </ul>
      </Specimen>
      <Specimen name="semantic roles" note="colour is spent like a signal">
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {ROLE_NAMES.map((role) => (
            <Swatch
              key={role}
              name={ROLE_MEANINGS[role]}
              hex={tokens.role[role]}
              caption={onSurface(tokens.role[role])}
            />
          ))}
        </ul>
      </Specimen>
      <Specimen name="type scale" note="Geist · Geist Mono for every numeral">
        <ul className="flex flex-col gap-3">
          {Object.entries(typeScale).map(([name, style]) => (
            <li key={name} className="flex items-baseline gap-4">
              <span className="w-24 shrink-0 num text-[12px] text-ink-muted">
                {name} {style.sizePx}/{style.linePx}
              </span>
              <span
                className={cn('min-w-0 flex-1 truncate text-ink', 'mono' in style && 'font-mono')}
                style={{
                  fontSize: `${style.sizePx}px`,
                  lineHeight: `${style.linePx}px`,
                  fontWeight: style.weight,
                  letterSpacing: 'tracking' in style ? style.tracking : undefined,
                  textTransform: 'uppercase' in style ? 'uppercase' : undefined,
                }}
              >
                {'mono' in style ? 'effect +0.75' : 'Blame the earliest step'}
              </span>
            </li>
          ))}
        </ul>
      </Specimen>
      <div className="flex flex-col gap-10">
        <Specimen name="radii" note="deliberately varied per surface">
          <ul className="flex flex-wrap gap-3">
            {Object.entries(radii).map(([name, value]) => (
              <li key={name} className="flex flex-col items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="block size-14 border border-line-strong bg-surface"
                  style={{ borderRadius: value === '999px' ? '999px' : value }}
                />
                <span className="num text-[11px] text-ink-muted">
                  {name} {value}
                </span>
              </li>
            ))}
          </ul>
        </Specimen>
        <Specimen name="springs" note="stiffness / damping / mass">
          <ul className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {Object.entries(springs).map(([name, spring]) => (
              <li key={name} className="flex justify-between gap-3">
                <span className="font-mono text-small text-ink">{name}</span>
                <span className="num text-small text-ink-muted">
                  {spring.stiffness} / {spring.damping} / {spring.mass}
                </span>
              </li>
            ))}
          </ul>
        </Specimen>
      </div>
    </div>
  )
}
