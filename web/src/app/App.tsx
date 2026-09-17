import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { MotionConfig } from 'motion/react'
import { useState } from 'react'

import { createQueryClient } from '@/api/queries'
import { TooltipProvider } from '@/components/primitives/Tooltip'

import { type AppRouter, createAppRouter } from './router'

interface AppProps {
  /** Tests pass a router on a memory history. */
  readonly router?: AppRouter
}

const TOOLTIP_DELAY_MS = 250

export function App({ router }: AppProps) {
  const [queryClient] = useState(createQueryClient)
  const [appRouter] = useState(() => router ?? createAppRouter())
  return (
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={TOOLTIP_DELAY_MS}>
          <RouterProvider router={appRouter} />
        </TooltipProvider>
      </QueryClientProvider>
    </MotionConfig>
  )
}
