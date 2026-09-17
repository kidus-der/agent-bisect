import {
  type RouterHistory,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
} from '@tanstack/react-router'

import { AppShell } from './AppShell'
import { RouteError, RouteNotFound, RoutePending } from './RouteError'

const rootRoute = createRootRoute({
  component: AppShell,
  errorComponent: RouteError,
  notFoundComponent: RouteNotFound,
})

// Every page is its own chunk; charts load only with the routes that draw them.
const overviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: lazyRouteComponent(() => import('@/pages/OverviewPage'), 'OverviewPage'),
  errorComponent: RouteError,
})
const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs',
  component: lazyRouteComponent(() => import('@/pages/RunsPage'), 'RunsPage'),
  errorComponent: RouteError,
})
const runDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs/$runId',
  component: lazyRouteComponent(() => import('@/pages/RunDetailPage'), 'RunDetailPage'),
  errorComponent: RouteError,
})
const benchmarkRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/benchmark',
  component: lazyRouteComponent(() => import('@/pages/BenchmarkPage'), 'BenchmarkPage'),
  errorComponent: RouteError,
})
const liveRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/live',
  component: lazyRouteComponent(() => import('@/pages/LivePage'), 'LivePage'),
  errorComponent: RouteError,
})
const prChecksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/pr-checks',
  component: lazyRouteComponent(() => import('@/pages/PrChecksPage'), 'PrChecksPage'),
  errorComponent: RouteError,
})
const galleryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/gallery',
  component: lazyRouteComponent(() => import('@/pages/gallery/GalleryPage'), 'GalleryPage'),
  errorComponent: RouteError,
})

const routeTree = rootRoute.addChildren([
  overviewRoute,
  runsRoute,
  runDetailRoute,
  benchmarkRoute,
  liveRoute,
  prChecksRoute,
  galleryRoute,
])

export function createAppRouter(history?: RouterHistory) {
  return createRouter({
    routeTree,
    history,
    defaultPreload: 'intent',
    defaultPendingComponent: RoutePending,
    scrollRestoration: true,
  })
}

export type AppRouter = ReturnType<typeof createAppRouter>

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter
  }
}
