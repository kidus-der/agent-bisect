/**
 * Design-evaluator capture pass.
 *
 * Captures every page of the dashboard at 1440x900 and 390x844, in dark and
 * light, plus the states a still of the happy path never shows: filtered,
 * mid-rewind, mid-replay, loading, error, 404, empty, recording, and the
 * signature motion moments as frame sequences.
 *
 * It drives the real app against the real `--fixture` API (no `page.route`
 * mocking except where the state being captured IS a network condition), so
 * what is scored is what a user would see, not what the tests stub.
 *
 * Output: docs/screenshots/round<N>/eval/<name>.png, N from EVAL_ROUND.
 */
import { fileURLToPath } from 'node:url'

import { type Locator, type Page, test } from '@playwright/test'

const ROUND = process.env.EVAL_ROUND ?? '1'
const OUT_DIR = fileURLToPath(
  new URL(`../../../docs/screenshots/round${ROUND}/eval/`, import.meta.url),
)

const THEME_KEY = 'bisect.theme'
type Theme = 'dark' | 'light'
const THEMES: readonly Theme[] = ['dark', 'light']

interface Viewport {
  readonly name: '1440' | '390'
  readonly width: number
  readonly height: number
}
const DESKTOP: Viewport = { name: '1440', width: 1440, height: 900 }
const MOBILE: Viewport = { name: '390', width: 390, height: 844 }
const VIEWPORTS: readonly Viewport[] = [DESKTOP, MOBILE]

/** Charts animate in on first view; give every entrance time to resolve. */
const SETTLE_MS = 2200
/**
 * One frame of a signature moment, sampled fast enough to read the easing and
 * long enough to cover a spring that takes most of a second to settle.
 */
const FRAME_MS = 50
const FRAME_COUNT = 24
/** Milliseconds after the rewind click at which the tape is worth a still. */
const REWIND_SAMPLE_MS = [250, 600, 1200, 2400] as const
/** Room for the page to grow into once the viewport is opened to its height. */
const TALL_MARGIN_PX = 40

/**
 * `full` captures everything. Otherwise EVAL_SCOPE is a comma-separated list of
 * page names still being scored, so a later round only re-shoots what can still
 * change and a page already at the bar stops costing anything.
 */
const SCOPE = process.env.EVAL_SCOPE ?? 'full'
const isFullScope = SCOPE === 'full'
const SCOPED_PAGES = new Set(SCOPE.split(',').map((name) => name.trim()))
const inScope = (name: string): boolean => isFullScope || SCOPED_PAGES.has(name)

/** Runs chosen for what they make the UI do, not for their contents. */
const RUNS = {
  /** The brief's worked example: 12 steps, planted fault at 7. */
  brief: 'brief-12-step',
  /** Long tape: does the timeline still work at 60 cells? */
  long: 'run-edge-60-step',
  /** Bisected, but no step's CI lower bound clears delta. */
  noClear: 'run-edge-no-clear',
  /** Failed, never bisected: zero tested steps. */
  zeroTested: 'run-edge-zero-tested',
  /** Still being recorded: no outcome yet. */
  recording: 'run-edge-recording-1',
} as const

const PR_REGRESSION = 'pr-check-00'
const PR_CLEAN = 'pr-check-03'

async function setTheme(page: Page, theme: Theme): Promise<void> {
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
    THEME_KEY,
    theme,
  ] as const)
}

/** Land on `path` with `theme` applied and everything on the page settled. */
async function open(
  page: Page,
  theme: Theme,
  viewport: Viewport,
  path: string,
  options: { readonly reduced?: boolean } = {},
): Promise<void> {
  await page.setViewportSize({ width: viewport.width, height: viewport.height })
  // Stills are judged on their final state; the moving frames get their own tests.
  await page.emulateMedia({ reducedMotion: options.reduced === false ? 'no-preference' : 'reduce' })
  await setTheme(page, theme)
  await page.goto(path)
  await page.getByRole('heading', { level: 1 }).waitFor()
  await page.waitForTimeout(SETTLE_MS)
}

async function shoot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${OUT_DIR}${name}.png` })
}

/**
 * Opens the viewport to the page's own height, then takes an ordinary shot.
 *
 * NOT `fullPage: true`: Playwright resizes the viewport underneath the running
 * page to stitch that capture, and visx's `ParentSize` re-measures while it is
 * happening — charts came out drawn at roughly a third of their real width, so
 * rounds 1-3 partly reviewed a plot the browser never showed. Resizing first
 * and letting it settle captures the chart at the width it was laid out for.
 */
async function shootWholePage(page: Page, name: string, width: number): Promise<void> {
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  await page.setViewportSize({ width, height: height + TALL_MARGIN_PX })
  await page.waitForTimeout(SETTLE_MS)
  await shoot(page, name)
}

/**
 * Above-the-fold AND whole-page, because the two answer different questions:
 * what greets you, and whether the page holds together all the way down.
 */
async function shootBoth(page: Page, stem: string, viewport: Viewport): Promise<void> {
  await shoot(page, `${stem}-fold`)
  await shootWholePage(page, `${stem}-full`, viewport.width)
  // Growing the viewport leaves it tall; put it back for whatever comes next.
  await page.setViewportSize({ width: viewport.width, height: viewport.height })
  await page.evaluate(() => window.scrollTo(0, 0))
}

/**
 * A signature moment, sampled from the instant it is triggered.
 *
 * The first frame is taken before any wait: sampling late makes every entrance
 * look like a cut, which is what made rounds 1-3 unable to tell a missing
 * animation from a fast one.
 */
async function captureFrames(page: Page, stem: string, target?: Locator): Promise<void> {
  const shot = target ?? page
  for (let index = 0; index < FRAME_COUNT; index += 1) {
    await shot.screenshot({ path: `${OUT_DIR}${stem}-f${String(index).padStart(2, '0')}.png` })
    await page.waitForTimeout(FRAME_MS)
  }
}

/**
 * An entrance that only plays once, on scroll-into-view: the panel has to start
 * below the fold, and sampling has to begin with the scroll that reveals it.
 */
async function captureEntrance(page: Page, stem: string, target: Locator): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(400)
  await target.scrollIntoViewIfNeeded()
  await captureFrames(page, stem)
}

// ---------------------------------------------------------------- static pages

/** Every page that is worth seeing in both themes at both widths. */
const PAGES = [
  { name: 'overview', path: '/', page: 'overview' },
  { name: 'runs', path: '/runs', page: 'runs' },
  {
    name: 'runs-filtered',
    path: '/runs?outcome=fail&domain=airline&fault=wrong_value',
    page: 'runs',
  },
  { name: 'run-detail-brief', path: `/runs/${RUNS.brief}`, page: 'run-detail' },
  { name: 'benchmark', path: '/benchmark', page: 'benchmark' },
  { name: 'pr-checks', path: '/pr-checks', page: 'pr-checks' },
  { name: 'pr-check-regression', path: `/pr-checks/${PR_REGRESSION}`, page: 'pr-checks' },
  { name: 'pr-check-clean', path: `/pr-checks/${PR_CLEAN}`, page: 'pr-checks' },
] as const

for (const theme of THEMES) {
  for (const viewport of VIEWPORTS) {
    for (const target of PAGES) {
      // A page already at the bar is not re-shot; it costs nothing this round.
      if (!inScope(target.page)) continue
      test(`${target.name} ${theme} ${viewport.name}`, async ({ page }) => {
        await open(page, theme, viewport, target.path)
        await shootBoth(page, `${target.name}-${theme}-${viewport.name}`, viewport)
      })
    }

    // Run-detail edge cases: the shapes of run that break a happy-path layout.
    if (isFullScope) {
      test(`run-detail edges ${theme} ${viewport.name}`, async ({ page }) => {
        for (const [name, runId] of [
          ['60step', RUNS.long],
          ['no-clear', RUNS.noClear],
          ['zero-tested', RUNS.zeroTested],
          ['recording', RUNS.recording],
        ] as const) {
          await open(page, theme, viewport, `/runs/${runId}`)
          await shootBoth(page, `run-detail-${name}-${theme}-${viewport.name}`, viewport)
        }
      })
    }

    /** Live only tells the truth once the stream has pushed more than once. */
    if (inScope('live')) {
      test(`live ${theme} ${viewport.name}`, async ({ page }) => {
        await open(page, theme, viewport, '/live')
        await page
          .getByText(/\b([2-9]|\d{2,}) updates\b/)
          .first()
          .waitFor({ timeout: 40_000 })
        await page.waitForTimeout(600)
        await shootBoth(page, `live-${theme}-${viewport.name}`, viewport)
      })
    }
  }

  // ------------------------------------------------------------ overlays
  // Shell chrome and the non-happy states belong to the `global` page.
  if (!inScope('global')) continue

  test(`palette ${theme} 1440`, async ({ page }) => {
    await open(page, theme, DESKTOP, '/runs')
    await page.keyboard.press('ControlOrMeta+k')
    await page.getByRole('dialog').waitFor()
    await page.keyboard.type('refund')
    await page.getByRole('option').first().waitFor()
    await page.waitForTimeout(400)
    await shoot(page, `palette-${theme}-1440`)
  })

  test(`palette ${theme} 390`, async ({ page }) => {
    await open(page, theme, MOBILE, '/runs')
    await page.keyboard.press('ControlOrMeta+k')
    await page.getByRole('dialog').waitFor()
    await page.keyboard.type('refund')
    await page.waitForTimeout(400)
    await shoot(page, `palette-${theme}-390`)
  })

  test(`runs filter sheet ${theme} 390`, async ({ page }) => {
    await open(page, theme, MOBILE, '/runs')
    await page
      .getByRole('button', { name: /Filters/ })
      .first()
      .click()
    await page.getByRole('dialog').waitFor()
    await page.waitForTimeout(500)
    await shoot(page, `runs-filter-sheet-${theme}-390`)
  })

  // ------------------------------------------------------------ non-happy states

  /** A slow API, so the skeleton is what is on screen rather than a flash of it. */
  test(`loading ${theme} 1440`, async ({ page }) => {
    await page.route('**/api/overview**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 15_000))
      await route.continue()
    })
    await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await setTheme(page, theme)
    await page.goto('/', { waitUntil: 'commit' })
    await page.waitForTimeout(1800)
    await shoot(page, `loading-overview-${theme}-1440`)
  })

  test(`error ${theme} 1440`, async ({ page }) => {
    await page.route('**/api/overview**', (route) => route.abort('connectionrefused'))
    await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await setTheme(page, theme)
    await page.goto('/')
    // Long enough for the query client to exhaust its retries and give up, so
    // what is captured is the settled error state rather than a still-retrying one.
    await page.waitForTimeout(20_000)
    await shoot(page, `error-overview-${theme}-1440`)
  })

  /**
   * Between the first failure and giving up: a dead server must not look like a
   * slow one, so the skeleton has to say it is retrying and how many tries are left.
   */
  test(`retrying ${theme} 1440`, async ({ page }) => {
    await page.route('**/api/overview**', (route) => route.abort('connectionrefused'))
    await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await setTheme(page, theme)
    await page.goto('/')
    await page.locator('[data-slot="retry-notice"]').first().waitFor({ timeout: 20_000 })
    await page.waitForTimeout(300)
    await shoot(page, `retrying-overview-${theme}-1440`)
  })

  test(`not-found ${theme} 1440`, async ({ page }) => {
    await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await setTheme(page, theme)
    await page.goto('/no-such-page')
    await page.waitForTimeout(1200)
    await shoot(page, `not-found-${theme}-1440`)
  })

  test(`runs empty ${theme} 1440`, async ({ page }) => {
    await open(page, theme, DESKTOP, '/runs?q=zzzzznothingmatchesthis')
    await shoot(page, `runs-empty-${theme}-1440`)
  })
}

// ---------------------------------------------------------------- the rewind

/** The rewind, caught while it plays: three frames plus a frame strip. */
if (inScope('run-detail'))
  test('rewind sequence dark 1440', async ({ page }) => {
    await open(page, 'dark', DESKTOP, `/runs/${RUNS.brief}`, { reduced: false })
    const tape = page.getByTestId('tape-lane')
    await tape.scrollIntoViewIfNeeded()
    await page.getByRole('button', { name: /Rewind to k=/ }).click()
    // Milliseconds since the click, and the wait that gets from the previous one to it.
    let elapsedMs = 0
    for (const sinceClickMs of REWIND_SAMPLE_MS) {
      await page.waitForTimeout(sinceClickMs - elapsedMs)
      elapsedMs = sinceClickMs
      await shoot(page, `rewind-dark-1440-t${sinceClickMs}`)
    }
    await page.reload()
    await page.getByRole('heading', { level: 1 }).waitFor()
    await page.waitForTimeout(SETTLE_MS)
    await page.getByRole('button', { name: /Rewind to k=/ }).click()
    await captureFrames(page, 'motion-rewind-dark-1440', tape)
  })

if (inScope('run-detail'))
  test('rewind sequence light 390', async ({ page }) => {
    await open(page, 'light', MOBILE, `/runs/${RUNS.brief}`, { reduced: false })
    await page.getByRole('button', { name: /Rewind to k=/ }).click()
    for (const delay of [400, 1400]) {
      await page.waitForTimeout(delay === 400 ? 400 : 1000)
      await shoot(page, `rewind-light-390-t${delay}`)
    }
  })

/** Reduced motion must land on the final state with no interstitial frames. */
if (inScope('run-detail'))
  test('rewind reduced motion dark 1440', async ({ page }) => {
    await open(page, 'dark', DESKTOP, `/runs/${RUNS.brief}`)
    await page.getByRole('button', { name: /Rewind to k=/ }).click()
    await page.waitForTimeout(120)
    await shoot(page, 'rewind-reduced-dark-1440-t120')
    await page.waitForTimeout(2000)
    await shoot(page, 'rewind-reduced-dark-1440-settled')
  })

/** A treated re-run, and the control it is measured against, at both widths. */
if (inScope('run-detail'))
  test('rerun view', async ({ page }) => {
    for (const theme of THEMES) {
      for (const viewport of VIEWPORTS) {
        for (const [arm, rerunId] of [
          ['treated', `${RUNS.brief}-t7-0`],
          ['control', `${RUNS.brief}-c-0`],
        ] as const) {
          await open(page, theme, viewport, `/runs/${RUNS.brief}/reruns/${rerunId}`)
          await shootBoth(page, `rerun-${arm}-${theme}-${viewport.name}`, viewport)
        }
      }
    }
  })

// ---------------------------------------------------------------- motion strips

/** Lands on `path` with motion left on, without the settle that eats entrances. */
async function openMoving(page: Page, path: string, theme: Theme = 'dark'): Promise<void> {
  await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await setTheme(page, theme)
  await page.goto(path)
  await page.getByRole('heading', { level: 1 }).waitFor()
}

if (inScope('run-detail'))
  test('motion: run-detail forest entrance', async ({ page }) => {
    await openMoving(page, `/runs/${RUNS.brief}`)
    await captureEntrance(page, 'motion-forest-dark-1440', page.getByText('Effect per tested step'))
  })

if (inScope('pr-checks'))
  test('motion: PR gate-history forest entrance', async ({ page }) => {
    await openMoving(page, '/pr-checks')
    await captureEntrance(
      page,
      'motion-pr-forest-dark-1440',
      page.getByText('What the gate has caught'),
    )
  })

if (inScope('benchmark'))
  test('motion: benchmark chart entrance', async ({ page }) => {
    await openMoving(page, '/benchmark')
    await captureFrames(page, 'motion-benchmark-dark-1440')
  })

if (inScope('overview'))
  test('motion: overview hero bars and KPI tickers', async ({ page }) => {
    await openMoving(page, '/')
    await captureFrames(page, 'motion-hero-dark-1440')
  })

if (inScope('runs'))
  test('motion: runs row stagger', async ({ page }) => {
    await openMoving(page, '/runs')
    await captureFrames(page, 'motion-runs-stagger-dark-1440')
  })

/**
 * The list -> detail morph, both ways. All three `layoutId` targets (the id
 * chip, the blame stripe, the status pill) travel in one transition, so the
 * whole viewport is sampled rather than any one of them.
 */
if (inScope('runs'))
  test('motion: runs row to run detail and back', async ({ page }) => {
    await openMoving(page, '/runs')
    await page.waitForTimeout(SETTLE_MS)
    // Rows navigate on click rather than being links, so the row itself is the target.
    await page.getByRole('row').filter({ hasText: RUNS.brief }).first().click()
    await captureFrames(page, 'motion-list-to-detail-dark-1440')
    await page.waitForTimeout(SETTLE_MS)
    await page.getByRole('link', { name: 'Runs' }).first().click()
    await captureFrames(page, 'motion-detail-to-list-dark-1440')
  })

if (inScope('global'))
  test('motion: palette open', async ({ page }) => {
    await openMoving(page, '/runs')
    await page.waitForTimeout(SETTLE_MS)
    await page.keyboard.press('ControlOrMeta+k')
    await captureFrames(page, 'motion-palette-dark-1440')
  })

/**
 * A page that is already at the bar but whose shared primitives changed: one
 * whole-page shot per theme, enough to see whether the change did any harm.
 */
for (const name of process.env.EVAL_SWEEP?.split(',').map((part) => part.trim()) ?? [])
  test(`sweep ${name}`, async ({ page }) => {
    const [route, theme] = name.split(':') as [string, Theme]
    await open(page, theme, DESKTOP, `/${route === 'overview' ? '' : route}`)
    await shootWholePage(page, `sweep-${route}-${theme}-1440-full`, DESKTOP.width)
  })

/** Reduced motion must land every entrance on its final state, instantly. */
test('motion: reduced-motion pass', async ({ page }) => {
  for (const [name, path] of [
    ['overview', '/'],
    ['runs', '/runs'],
    ['pr-checks', '/pr-checks'],
  ] as const) {
    await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await setTheme(page, 'dark')
    await page.goto(path)
    await page.getByRole('heading', { level: 1 }).waitFor()
    await page.waitForTimeout(250)
    await shoot(page, `reduced-${name}-dark-1440-immediate`)
  }
})
