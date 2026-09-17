/**
 * P6 gate: the curated final screenshot set for docs/screenshots/final/.
 *
 * Everything the design evaluator captured (docs/screenshots/round5|round6/)
 * was shot against a Vite dev server proxying a separate fixture API
 * (evaluator.config.ts's documented two-process setup). This is the same
 * "real app, real fixture data, no page.route mocking" method, pointed
 * instead at the one process that actually ships: `bisect serve --fixture`
 * serving the production static build. It exists to catch anything that
 * differs between the dev and release builds, not to re-score design.
 *
 * Output: docs/screenshots/final/<name>.png
 *
 *   uv run bisect serve --fixture --port 8500
 *   cd web && FINAL_BASE_URL=http://127.0.0.1:8500 \
 *     npx playwright test --config e2e/capture/final.config.ts
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

/** The brief's worked example: 12 steps, planted fault at 7 -- what every page opens on by default. */
const BRIEF_RUN = 'brief-12-step'
const PR_CHECK = 'pr-check-00'

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
  await open(page, 'dark', DESKTOP, `/runs/${BRIEF_RUN}`)
  await shootWholePage(page, 'run-detail-dark-1440', DESKTOP.width)
})

test('run detail light 1440', async ({ page }) => {
  await open(page, 'light', DESKTOP, `/runs/${BRIEF_RUN}`)
  await shootWholePage(page, 'run-detail-light-1440', DESKTOP.width)
})

test('run detail dark 390', async ({ page }) => {
  await open(page, 'dark', MOBILE, `/runs/${BRIEF_RUN}`)
  await shootWholePage(page, 'run-detail-dark-390', MOBILE.width)
})

test('run detail rewind dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, `/runs/${BRIEF_RUN}`)
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
  await open(page, 'dark', DESKTOP, `/pr-checks/${PR_CHECK}`)
  await shootWholePage(page, 'pr-check-detail-dark-1440', DESKTOP.width)
})

test('palette dark 1440', async ({ page }) => {
  await open(page, 'dark', DESKTOP, '/runs')
  await page.keyboard.press('ControlOrMeta+k')
  await page.getByRole('dialog').waitFor()
  await page.keyboard.type('refund')
  await page.getByRole('option').first().waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: '../docs/screenshots/final/palette-dark-1440.png' })
})
