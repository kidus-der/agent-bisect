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
/** One frame of a signature moment, sampled fast enough to read the easing. */
const FRAME_MS = 70
const FRAME_COUNT = 10
/** Milliseconds after the rewind click at which the tape is worth a still. */
const REWIND_SAMPLE_MS = [250, 600, 1200, 2400] as const

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

async function shoot(page: Page, name: string, fullPage = false): Promise<void> {
  await page.screenshot({ path: `${OUT_DIR}${name}.png`, fullPage })
}

/**
 * Above-the-fold AND whole-page, because the two answer different questions:
 * what greets you, and whether the page holds together all the way down.
 */
async function shootBoth(page: Page, stem: string): Promise<void> {
  await shoot(page, `${stem}-fold`, false)
  // A full-page shot resizes the viewport; scroll back so the next shot is clean.
  await shoot(page, `${stem}-full`, true)
  await page.evaluate(() => window.scrollTo(0, 0))
}

/** A signature moment, sampled as a strip of frames while it plays. */
async function captureFrames(page: Page, stem: string, target?: Locator): Promise<void> {
  const shot = target ?? page
  for (let index = 0; index < FRAME_COUNT; index += 1) {
    await shot.screenshot({ path: `${OUT_DIR}${stem}-f${String(index).padStart(2, '0')}.png` })
    await page.waitForTimeout(FRAME_MS)
  }
}

// ---------------------------------------------------------------- static pages

/** Every page that is worth seeing in both themes at both widths. */
const PAGES = [
  { name: 'overview', path: '/' },
  { name: 'runs', path: '/runs' },
  { name: 'runs-filtered', path: '/runs?outcome=fail&domain=airline&fault=wrong_value' },
  { name: 'run-detail-brief', path: `/runs/${RUNS.brief}` },
  { name: 'benchmark', path: '/benchmark' },
  { name: 'pr-checks', path: '/pr-checks' },
  { name: 'pr-check-regression', path: `/pr-checks/${PR_REGRESSION}` },
  { name: 'pr-check-clean', path: `/pr-checks/${PR_CLEAN}` },
] as const

for (const theme of THEMES) {
  for (const viewport of VIEWPORTS) {
    for (const target of PAGES) {
      test(`${target.name} ${theme} ${viewport.name}`, async ({ page }) => {
        await open(page, theme, viewport, target.path)
        await shootBoth(page, `${target.name}-${theme}-${viewport.name}`)
      })
    }

    // Run-detail edge cases: the shapes of run that break a happy-path layout.
    test(`run-detail edges ${theme} ${viewport.name}`, async ({ page }) => {
      for (const [name, runId] of [
        ['60step', RUNS.long],
        ['no-clear', RUNS.noClear],
        ['zero-tested', RUNS.zeroTested],
        ['recording', RUNS.recording],
      ] as const) {
        await open(page, theme, viewport, `/runs/${runId}`)
        await shootBoth(page, `run-detail-${name}-${theme}-${viewport.name}`)
      }
    })

    /** Live only tells the truth once the stream has pushed more than once. */
    test(`live ${theme} ${viewport.name}`, async ({ page }) => {
      await open(page, theme, viewport, '/live')
      await page
        .getByText(/\b([2-9]|\d{2,}) updates\b/)
        .first()
        .waitFor({ timeout: 40_000 })
      await page.waitForTimeout(600)
      await shootBoth(page, `live-${theme}-${viewport.name}`)
    })
  }

  // ------------------------------------------------------------ overlays

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

test('rewind sequence light 390', async ({ page }) => {
  await open(page, 'light', MOBILE, `/runs/${RUNS.brief}`, { reduced: false })
  await page.getByRole('button', { name: /Rewind to k=/ }).click()
  for (const delay of [400, 1400]) {
    await page.waitForTimeout(delay === 400 ? 400 : 1000)
    await shoot(page, `rewind-light-390-t${delay}`)
  }
})

/** Reduced motion must land on the final state with no interstitial frames. */
test('rewind reduced motion dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, `/runs/${RUNS.brief}`)
  await page.getByRole('button', { name: /Rewind to k=/ }).click()
  await page.waitForTimeout(120)
  await shoot(page, 'rewind-reduced-dark-1440-t120')
  await page.waitForTimeout(2000)
  await shoot(page, 'rewind-reduced-dark-1440-settled')
})

test('rerun view both themes 1440', async ({ page }) => {
  for (const theme of THEMES) {
    await open(page, theme, DESKTOP, `/runs/${RUNS.brief}/reruns/${RUNS.brief}-t7-0`)
    await shootBoth(page, `rerun-${theme}-1440`)
  }
})

// ---------------------------------------------------------------- motion strips

test('motion: forest plot entrance', async ({ page }) => {
  await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await setTheme(page, 'dark')
  await page.goto(`/runs/${RUNS.brief}`)
  await page.getByRole('heading', { level: 1 }).waitFor()
  await captureFrames(page, 'motion-forest-dark-1440')
})

test('motion: overview hero bars and tickers', async ({ page }) => {
  await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await setTheme(page, 'dark')
  await page.goto('/')
  await page.getByRole('heading', { level: 1 }).waitFor()
  await captureFrames(page, 'motion-hero-dark-1440')
})

test('motion: palette open', async ({ page }) => {
  await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await setTheme(page, 'dark')
  await page.goto('/runs')
  await page.getByRole('heading', { level: 1 }).waitFor()
  await page.waitForTimeout(SETTLE_MS)
  await page.keyboard.press('ControlOrMeta+k')
  await captureFrames(page, 'motion-palette-dark-1440')
})

test('motion: runs row to run detail', async ({ page }) => {
  await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await setTheme(page, 'dark')
  await page.goto('/runs')
  await page.getByRole('heading', { level: 1 }).waitFor()
  await page.waitForTimeout(SETTLE_MS)
  // Rows navigate on click rather than being links, so the row itself is the target.
  await page.getByRole('row').filter({ hasText: RUNS.brief }).first().click()
  await captureFrames(page, 'motion-list-to-detail-dark-1440')
})

/** The whole overview with motion left on, to confirm nothing ends mid-flight. */
test('overview reduced-motion parity dark 1440', async ({ page }) => {
  await page.setViewportSize({ width: DESKTOP.width, height: DESKTOP.height })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await setTheme(page, 'dark')
  await page.goto('/')
  await page.getByRole('heading', { level: 1 }).waitFor()
  // No settle: reduced motion must have painted its final state already.
  await page.waitForTimeout(250)
  await shoot(page, 'reduced-overview-dark-1440-immediate')
})
