/**
 * P6 real-data finalization: the same curated screenshot set as
 * final-capture.ts, re-shot against `bisect serve --real` serving the
 * production build, so docs/screenshots/final/ shows real recordings
 * instead of the seeded fixture. Same 12 names, same method (real app,
 * real API, no page.route mocking, viewport opened to the page's own
 * height before an ordinary screenshot -- never `fullPage`, see
 * final-capture.ts's own note on the visx `ParentSize` re-measure artefact).
 *
 * Run id / PR check id / search term are env vars, not hard-coded, because
 * real mode has no fixed "brief-12-step" worked example -- pick a real
 * diagnosed run (one file under runs/blame/) and a real gate check
 * (one directory under runs/p7/local/).
 *
 *   uv run bisect serve --real --port 8498
 *   cd web && REAL_FINAL_BASE_URL=http://127.0.0.1:8498 \
 *     REAL_RUN_ID=airline-17-t0-a4-k4-tool_error-s0 \
 *     REAL_PR_CHECK_ID=demo_p7-id-slip-100 \
 *     REAL_SEARCH_TERM=airline-17 \
 *     npx playwright test --config e2e/capture/real-final.config.ts
 */
import { type Page, test } from '@playwright/test'

const THEME_KEY = 'bisect.theme'
type Theme = 'dark' | 'light'

interface Viewport {
  readonly width: number
  readonly height: number
}
const DESKTOP: Viewport = { width: 1440, height: 900 }
const MOBILE: Viewport = { width: 390, height: 844 }

/** Charts animate in on first view; give every entrance time to resolve. */
const SETTLE_MS = 2200
/** Room for the page to grow into once the viewport is opened to its height. */
const TALL_MARGIN_PX = 40

const RUN_ID = process.env.REAL_RUN_ID ?? ''
const PR_CHECK_ID = process.env.REAL_PR_CHECK_ID ?? ''
const SEARCH_TERM = process.env.REAL_SEARCH_TERM ?? ''

async function setTheme(page: Page, theme: Theme): Promise<void> {
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
    THEME_KEY,
    theme,
  ] as const)
}

async function open(page: Page, theme: Theme, viewport: Viewport, path: string): Promise<void> {
  await page.setViewportSize(viewport)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await setTheme(page, theme)
  await page.goto(path)
  await page.getByRole('heading', { level: 1 }).waitFor()
  await page.waitForTimeout(SETTLE_MS)
}

/**
 * Opens the viewport to the page's own height, then takes an ordinary shot.
 *
 * NOT `fullPage: true`: see evaluator-capture.ts's `shootWholePage` for why --
 * the same visx `ParentSize` re-measure artefact applies here.
 */
async function shootWholePage(page: Page, name: string, width: number): Promise<void> {
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  await page.setViewportSize({ width, height: height + TALL_MARGIN_PX })
  await page.waitForTimeout(SETTLE_MS)
  await page.screenshot({ path: `../docs/screenshots/final/${name}.png` })
}

test('overview dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, '/')
  await shootWholePage(page, 'overview-dark-1440', DESKTOP.width)
})

test('overview light 1440', async ({ page }) => {
  await open(page, 'light', DESKTOP, '/')
  await shootWholePage(page, 'overview-light-1440', DESKTOP.width)
})

test('overview dark 390', async ({ page }) => {
  await open(page, 'dark', MOBILE, '/')
  await shootWholePage(page, 'overview-dark-390', MOBILE.width)
})

test('runs dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, '/runs')
  await shootWholePage(page, 'runs-dark-1440', DESKTOP.width)
})

test('run detail dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, `/runs/${RUN_ID}`)
  await shootWholePage(page, 'run-detail-dark-1440', DESKTOP.width)
})

test('run detail light 1440', async ({ page }) => {
  await open(page, 'light', DESKTOP, `/runs/${RUN_ID}`)
  await shootWholePage(page, 'run-detail-light-1440', DESKTOP.width)
})

test('run detail dark 390', async ({ page }) => {
  await open(page, 'dark', MOBILE, `/runs/${RUN_ID}`)
  await shootWholePage(page, 'run-detail-dark-390', MOBILE.width)
})

test('run detail rewind dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, `/runs/${RUN_ID}`)
  await page.getByRole('button', { name: /Rewind to k=/ }).click()
  await page.waitForTimeout(1200)
  await page.screenshot({ path: '../docs/screenshots/final/run-detail-rewind-dark-1440.png' })
})

test('benchmark dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, '/benchmark')
  await shootWholePage(page, 'benchmark-dark-1440', DESKTOP.width)
})

test('live dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, '/live')
  await page
    .getByText(/\b([2-9]|\d{2,}) updates\b/)
    .first()
    .waitFor({ timeout: 40_000 })
  await page.waitForTimeout(600)
  await shootWholePage(page, 'live-dark-1440', DESKTOP.width)
})

test('pr check detail dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, `/pr-checks/${PR_CHECK_ID}`)
  await shootWholePage(page, 'pr-check-detail-dark-1440', DESKTOP.width)
})

test('palette dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, '/runs')
  await page.keyboard.press('ControlOrMeta+k')
  await page.getByRole('dialog').waitFor()
  await page.keyboard.type(SEARCH_TERM)
  await page.getByRole('option').first().waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: '../docs/screenshots/final/palette-dark-1440.png' })
})
