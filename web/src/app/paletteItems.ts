import { ClipboardCopy, type LucideIcon, SunMoon, SwatchBook } from 'lucide-react'

import { CLI_COMMANDS, NAV_ITEMS } from './nav'

export type PaletteAction =
  | { readonly kind: 'navigate'; readonly to: string }
  | { readonly kind: 'toggle-theme' }
  | { readonly kind: 'copy'; readonly text: string }

export interface PaletteItem {
  readonly id: string
  readonly group: 'Pages' | 'Commands' | 'Copy CLI command'
  readonly label: string
  readonly icon: LucideIcon
  /** Shown in the detail pane. */
  readonly detail: string
  /** Literal machine text for the detail pane: a path or a shell line. */
  readonly token: string
  readonly keywords: readonly string[]
  readonly action: PaletteAction
}

const PAGE_ITEMS: readonly PaletteItem[] = NAV_ITEMS.map((item) => ({
  id: `page:${item.to}`,
  group: 'Pages',
  label: item.label,
  icon: item.icon,
  detail: item.description,
  token: item.to,
  keywords: ['go', 'jump', 'open'],
  action: { kind: 'navigate', to: item.to },
}))

const GALLERY_ITEM: PaletteItem = {
  id: 'page:/gallery',
  group: 'Pages',
  label: 'Gallery',
  icon: SwatchBook,
  detail: 'Kitchen sink of every primitive, state and chart in the current theme.',
  token: '/gallery',
  keywords: ['design', 'components', 'kitchen sink'],
  action: { kind: 'navigate', to: '/gallery' },
}

const COMMAND_ITEMS: readonly PaletteItem[] = [
  {
    id: 'command:toggle-theme',
    group: 'Commands',
    label: 'Toggle theme',
    icon: SunMoon,
    detail: 'Switch between the dark and light themes. The choice is remembered on this machine.',
    token: 'data-theme',
    keywords: ['dark', 'light', 'appearance'],
    action: { kind: 'toggle-theme' },
  },
]

const COPY_ITEMS: readonly PaletteItem[] = CLI_COMMANDS.map((entry) => ({
  id: `copy:${entry.command}`,
  group: 'Copy CLI command',
  label: entry.label,
  icon: ClipboardCopy,
  detail: 'Copies this command to the clipboard.',
  token: `$ ${entry.command}`,
  keywords: ['cli', 'terminal', 'copy', entry.command],
  action: { kind: 'copy', text: entry.command },
}))

export const PALETTE_ITEMS: readonly PaletteItem[] = [
  ...PAGE_ITEMS,
  GALLERY_ITEM,
  ...COMMAND_ITEMS,
  ...COPY_ITEMS,
]

export const PALETTE_GROUPS = ['Pages', 'Commands', 'Copy CLI command'] as const
