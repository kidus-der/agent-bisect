import { Moon, Sun } from 'lucide-react'

import { Tooltip } from '@/components/primitives/Tooltip'
import { useTheme } from '@/design/theme'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const Icon = theme === 'dark' ? Moon : Sun
  return (
    <Tooltip content={`Switch to ${next} theme`} side="bottom">
      <button
        type="button"
        onClick={toggle}
        aria-label={`Switch to ${next} theme`}
        className="inline-flex size-10 cursor-pointer items-center justify-center rounded-control text-ink-muted hover:bg-elevated hover:text-ink"
      >
        <Icon aria-hidden="true" className="size-4" />
      </button>
    </Tooltip>
  )
}
