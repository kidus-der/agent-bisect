import { Link, useRouterState } from '@tanstack/react-router'
import { Search } from 'lucide-react'
import { motion } from 'motion/react'

import { Kbd } from '@/components/primitives/Kbd'
import { layoutIds, useSpringTransition } from '@/design/motion'
import { cn } from '@/lib/utils'

import { ActivityPulse } from './ActivityPulse'
import { useRunningJobCount } from './useRunningJobCount'
import { BrandMark } from './BrandMark'
import { DataSourceFlag } from './DataSourceFlag'
import { NAV_ITEMS, isNavItemActive } from './nav'
import { ThemeToggle } from './ThemeToggle'

interface TopBarProps {
  readonly onOpenPalette: () => void
}

function DesktopNav() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const transition = useSpringTransition('snap')
  const runningJobs = useRunningJobCount()
  return (
    <nav aria-label="Primary" className="hidden h-full md:flex">
      <ul className="flex h-full items-stretch gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isNavItemActive(item, pathname)
          return (
            <li key={item.to} className="flex">
              <Link
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'relative inline-flex items-center rounded-control px-3 text-small font-medium',
                  active ? 'text-ink' : 'text-ink-muted hover:text-ink',
                )}
              >
                {item.label}
                {item.to === '/live' ? (
                  <ActivityPulse count={runningJobs} className="ml-1.5" />
                ) : null}
                {active ? (
                  <motion.span
                    layoutId={layoutIds.navIndicator}
                    transition={transition}
                    className="absolute inset-x-3 -bottom-px h-0.5 bg-ink"
                  />
                ) : null}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

/** Blueprint §5: brand, five destinations, then the palette and theme controls. */
export function TopBar({ onOpenPalette }: TopBarProps) {
  return (
    <header className="sticky top-0 z-(--z-nav) border-b border-line bg-ground/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 lg:gap-8 lg:px-8">
        <Link
          to="/"
          className="flex items-center gap-2.5 rounded-control"
          aria-label="Bisect, overview"
        >
          <BrandMark />
          <span className="text-[17px] font-semibold tracking-tight text-ink">Bisect</span>
        </Link>
        <DesktopNav />
        <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
          <DataSourceFlag />
          <button
            type="button"
            onClick={onOpenPalette}
            aria-label="Open command palette"
            aria-keyshortcuts="Meta+K Control+K"
            className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-control border border-line bg-surface px-3 text-small text-ink-muted hover:border-line-strong hover:text-ink lg:w-56"
          >
            <Search aria-hidden="true" className="size-4 shrink-0" />
            <span className="hidden flex-1 text-left lg:inline">Jump to…</span>
            <span className="hidden items-center gap-0.5 sm:inline-flex">
              <Kbd>⌘</Kbd>
              <Kbd>K</Kbd>
            </span>
          </button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
