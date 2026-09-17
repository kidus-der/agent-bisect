import { Link, useRouterState } from '@tanstack/react-router'

import { cn } from '@/lib/utils'

import { ActivityPulse, useRunningJobCount } from './ActivityPulse'
import { NAV_ITEMS, isNavItemActive } from './nav'

/**
 * Below 768px the top nav collapses into a fixed bottom tab bar: five
 * destinations, icon + label, thumb-reachable, 56px tall hit targets.
 */
export function BottomNav() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const runningJobs = useRunningJobCount()
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-(--z-nav) border-t border-line bg-ground/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
    >
      <ul className="grid grid-cols-5">
        {NAV_ITEMS.map((item) => {
          const active = isNavItemActive(item, pathname)
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'relative flex h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium -outline-offset-2',
                  active ? 'text-ink' : 'text-ink-muted',
                )}
              >
                {active ? <span className="absolute inset-x-5 top-0 h-0.5 bg-ink" /> : null}
                <span className="relative">
                  <item.icon aria-hidden="true" className="size-[18px]" />
                  {item.to === '/live' ? (
                    <ActivityPulse count={runningJobs} className="absolute -top-0.5 -right-1" />
                  ) : null}
                </span>
                {item.shortLabel}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
