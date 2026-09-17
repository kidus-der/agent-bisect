import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

import { typeScale } from '@/design/tokens'

/**
 * tailwind-merge only knows Tailwind's stock font sizes. `text-small`,
 * `text-h2`, `text-stat` and the rest of `typeScale` look like arbitrary
 * `text-*` utilities to it, so it files them under text *colour* — and
 * `cn('text-small text-ink')` silently dropped the size. Teaching it the scale
 * keeps size and colour in different conflict groups, so both survive.
 */
const FONT_SIZES = Object.keys(typeScale)

const twMerge = extendTailwindMerge({
  extend: { classGroups: { 'font-size': [{ text: FONT_SIZES }] } },
})

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
