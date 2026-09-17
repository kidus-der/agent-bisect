import {
  Activity,
  FlaskConical,
  GitPullRequest,
  LayoutGrid,
  type LucideIcon,
  ListTree,
} from 'lucide-react'

export interface NavItem {
  readonly to: '/' | '/runs' | '/benchmark' | '/live' | '/pr-checks'
  readonly label: string
  /** Shorter label for the 390px bottom bar. */
  readonly shortLabel: string
  readonly icon: LucideIcon
  readonly description: string
  /** Overview must match exactly; the others also match their children (/runs/:id). */
  readonly exact: boolean
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    to: '/',
    label: 'Overview',
    shortLabel: 'Overview',
    icon: LayoutGrid,
    description: 'Headline result: treated vs control with intervals.',
    exact: true,
  },
  {
    to: '/runs',
    label: 'Runs',
    shortLabel: 'Runs',
    icon: ListTree,
    description: 'Every recorded run; open one to scrub its tape.',
    exact: false,
  },
  {
    to: '/benchmark',
    label: 'Benchmark',
    shortLabel: 'Bench',
    icon: FlaskConical,
    description: 'Blame accuracy against planted faults, by method.',
    exact: false,
  },
  {
    to: '/live',
    label: 'Live',
    shortLabel: 'Live',
    icon: Activity,
    description: 'Jobs in flight, call budget and rate-limit headroom.',
    exact: false,
  },
  {
    to: '/pr-checks',
    label: 'PR checks',
    shortLabel: 'PRs',
    icon: GitPullRequest,
    description: 'Base vs head pass rate and the decisive step.',
    exact: false,
  },
]

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.exact
    ? pathname === item.to
    : pathname === item.to || pathname.startsWith(`${item.to}/`)
}

export const CLI_COMMANDS: readonly { readonly label: string; readonly command: string }[] = [
  { label: 'Check setup', command: 'bisect doctor' },
  { label: 'Record runs', command: 'bisect record --domain airline --tasks 0-19' },
  { label: 'Replay a run from tape', command: 'bisect replay RUN_ID' },
  { label: 'Blame a failed run', command: 'bisect blame RUN_ID --top 3 --n 8' },
  { label: 'Evaluate on the benchmark', command: 'bisect eval --split test' },
  { label: 'Gate a pull request', command: 'bisect gate --base main --head HEAD' },
]
