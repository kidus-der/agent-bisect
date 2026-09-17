import { Outlet, useRouterState } from '@tanstack/react-router'
import { LayoutGroup, motion } from 'motion/react'
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'

import { useSpringTransition } from '@/design/motion'

import { BottomNav } from './BottomNav'
import { TopBar } from './TopBar'

// cmdk + the dialog stay out of the initial bundle until the palette is first opened.
const CommandPalette = lazy(() =>
  import('./CommandPalette').then((module) => ({ default: module.CommandPalette })),
)

const MAIN_ID = 'main'
const PAGE_ENTER_OFFSET_PX = 8

function usePaletteShortcut(onToggle: () => void): void {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        onToggle()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onToggle])
}

/** SPA navigation must move focus, or keyboard and screen-reader users never learn the page changed. */
function useFocusMainOnNavigate(
  mainRef: React.RefObject<HTMLElement | null>,
  pathname: string,
): void {
  const previousPathname = useRef(pathname)
  useEffect(() => {
    if (previousPathname.current === pathname) return
    previousPathname.current = pathname
    mainRef.current?.focus({ preventScroll: true })
  }, [mainRef, pathname])
}

export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteLoaded, setPaletteLoaded] = useState(false)
  // Keyed on the matched route, not the URL: /runs/a -> /runs/b keeps its subtree mounted.
  const routeId = useRouterState({ select: (state) => state.matches.at(-1)?.routeId ?? '' })
  // Resolved = the new route has rendered; focusing earlier would land on the outgoing <main>.
  const resolvedPathname = useRouterState({
    select: (state) => state.resolvedLocation?.pathname ?? state.location.pathname,
  })
  const mainRef = useRef<HTMLElement | null>(null)
  const transition = useSpringTransition('settle')

  const openPalette = useCallback((): void => {
    setPaletteLoaded(true)
    setPaletteOpen(true)
  }, [])
  const togglePalette = useCallback((): void => {
    setPaletteLoaded(true)
    setPaletteOpen((open) => !open)
  }, [])
  usePaletteShortcut(togglePalette)
  useFocusMainOnNavigate(mainRef, resolvedPathname)

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href={`#${MAIN_ID}`}
        className="fixed top-2 left-2 z-(--z-skip-link) -translate-y-16 rounded-control bg-ink px-3 py-2 text-small font-medium text-ground focus-visible:translate-y-0"
      >
        Skip to content
      </a>
      <TopBar onOpenPalette={openPalette} />
      {/* One LayoutGroup so shared layoutIds morph across route changes. */}
      <LayoutGroup>
        <motion.main
          id={MAIN_ID}
          key={routeId}
          ref={mainRef}
          tabIndex={-1}
          initial={{ opacity: 0, y: PAGE_ENTER_OFFSET_PX }}
          animate={{ opacity: 1, y: 0 }}
          transition={transition}
          className="mx-auto w-full max-w-[1600px] flex-1 px-4 pt-6 pb-24 outline-none md:pb-16 lg:px-8 lg:pt-8"
        >
          <Outlet />
        </motion.main>
      </LayoutGroup>
      <BottomNav />
      {paletteLoaded ? (
        <Suspense fallback={null}>
          <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
        </Suspense>
      ) : null}
    </div>
  )
}
